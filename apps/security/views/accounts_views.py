# apps/security/views/accounts_views.py
import uuid
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth.forms import SetPasswordForm

from apps.security.permissions import AccountsPermissions
from apps.shared.apps_config import AppIdentifier
from apps.security.decorators import axentra_module_gate
from apps.security.models import UserProfile
from apps.security.models.organigrama import Dependencia, Sede
from apps.security.selectors.accounts_selectors import AccountsDashboardSelectors, FuncionarioSelectors
from apps.security.services.accounts_services import FuncionarioService
from apps.security.forms import (
    StaffUserCreationForm, StaffUserProfileForm,
    StaffUserChangeForm, StaffUserProfileChangeForm
)

from apps.shared.utils.telemetry import AxentraRadar

User = get_user_model()
logger = logging.getLogger(__name__)

_ETIQUETAS_CAMPO = {
    'email': 'Correo electrónico', 'first_name': 'Nombre(s)', 'last_name': 'Apellidos',
    'phone': 'Teléfono', 'area_id': 'Área', 'puesto': 'Puesto', 'telefono_oficina': 'Teléfono de oficina',
}


def _mensaje_legible(errores: dict) -> str:
    """Traduce el dict de errores de FuncionarioService a un mensaje mostrable.

    crear_funcionario/editar_funcionario devuelven una de varias formas según
    dónde falló la validación (DTO Pydantic, validador de contraseña de
    Django, error de negocio con clave propia) — sin esto, cualquier cosa
    que no traiga 'server_error' se mostraba como un mensaje genérico que no
    dice qué campo falló ni por qué.
    """
    if not errores:
        return 'Error de consistencia interna'
    if 'server_error' in errores:
        return errores['server_error'][0]
    if 'password' in errores:
        return ' '.join(errores['password'])
    if 'validation_errors' in errores:
        partes = []
        for error in errores['validation_errors']:
            campo = str(error.get('loc', ['dato'])[0])
            etiqueta = _ETIQUETAS_CAMPO.get(campo, campo)
            partes.append(f"{etiqueta}: {error.get('msg', 'valor inválido')}.")
        return ' '.join(partes) if partes else 'Revisa los datos capturados.'
    # Forma residual: {'clave_de_negocio': ['mensaje', ...]}
    primer_valor = next(iter(errores.values()), None)
    if isinstance(primer_valor, list) and primer_valor:
        return str(primer_valor[0])
    return 'Error de consistencia interna'

@login_required
@axentra_module_gate(module_identifier=AppIdentifier.ACCOUNTS, required_fine_permission="can_view_analytics")
def accounts_analytics_view(request):
    """CONSOLA ANALÍTICA DE PERSONAL (Métricas y Cronología de Altas)"""
    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    # Aislamiento de lógica analítica pesada mediante selectores
    context = AccountsDashboardSelectors.obtener_metricas_plantilla()
    context["cronologia_altas"] = AccountsDashboardSelectors.obtener_cronologia_altas()
    context.update({
        "modulo_actual": AppIdentifier.ACCOUNTS,
        "show_module_sidebar": False,
    })

    # Registro Forense y Telemetría en el Radar
    if AxentraRadar.enabled():
        AxentraRadar.imprimir_auditoria(
            componente="accounts_dashboard",
            request=request,
            titulo="Acceso a consola analítica de personal",
            icono="📊",
            extra_data={
                "¿Es HTMX?": is_htmx,
                "HX-Target": target_htmx if target_htmx else "F5 / URL directa",
                "Sidebar Secundario": context["show_module_sidebar"],
            },
        )

    if is_htmx:
        if target_htmx == "workbench":
            return render(request, "accounts/workbench/accounts_dashboard_workbench.html", context)
        # page-content o fallback preventivo (cualquier otro target HTMX)
        return render(request, "accounts/content/accounts_dashboard_content.html", context)

    return render(request, "accounts/pages/accounts_dashboard.html", context)


# =========================================================================
# PILAR UNIQUE: GESTIÓN DE EXPEDIENTES Y SERVIDORES PÚBLICOS
# =========================================================================
@login_required
@axentra_module_gate(AppIdentifier.ACCOUNTS, required_fine_permission="can_view_list")
def funcionario_list_view(request):
    """
    Controlador de padrón de funcionarios.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    context = build_funcionario_list_context(request)

    if is_htmx and target_htmx == "workbench":
        return render(
            request,
            "accounts/workbench/funcionario_list_workbench.html",
            context,
        )

    if is_htmx and target_htmx == "page-content":
        return render(
            request,
            "accounts/content/funcionario_list_content.html",
            context,
        )

    if is_htmx and target_htmx == "funcionario-results":
        return render(
            request,
            "accounts/htmx/funcionario_results.html",
            context,
        )

    return render(
        request,
        "accounts/pages/funcionario_list.html",
        context,
    )

def build_funcionario_list_context(request):
    """
    Construye el contexto oficial del listado de funcionarios.

    Debe usarse cada vez que una acción HTMX regrese al listado,
    por ejemplo: baja lógica, creación, filtros o regreso desde expediente.
    """

    search_query = request.GET.get("q", "").strip()
    sede_id = request.GET.get("sede", "").strip()
    dependencia_id = request.GET.get("dependencia", "").strip()

    funcionarios = FuncionarioSelectors.listar_plantilla_activa(
        search_query=search_query,
        sede_id=sede_id if sede_id.lower() not in ["all", ""] else "",
        dependencia_id=dependencia_id if dependencia_id.lower() not in ["all", ""] else "",
    )

    if getattr(request, "axentra_is_root", False) or not getattr(request.user, "axentra_profile", None):
        sedes = (
            Sede.objects
            .filter(is_deleted=False)
            .order_by("nombre")
        )

        dependencias = (
            Dependencia.objects
            .filter(is_deleted=False)
            .order_by("nombre")
        )

    else:
        profile = request.user.axentra_profile

        sedes = (
            Sede.objects
            .filter(
                id=profile.area.sede_fisica_id,
                is_deleted=False,
            )
            if getattr(profile, "area", None) and profile.area.sede_fisica_id
            else Sede.objects.none()
        )

        dependencias = (
            Dependencia.objects
            .filter(
                id=profile.area.dependencia_id,
                is_deleted=False,
            )
            if getattr(profile, "area", None) and profile.area.dependencia_id
            else Dependencia.objects.none()
        )

    return {
        "funcionarios": funcionarios,
        "sedes": sedes,
        "dependencias": dependencias,
        "current_q": search_query,
        "current_sede": request.GET.get("sede", ""),
        "current_dep": request.GET.get("dependencia", ""),
        "modulo_actual": AppIdentifier.ACCOUNTS,
        "show_module_sidebar": False,
    }


@login_required
@axentra_module_gate(AppIdentifier.ACCOUNTS, required_fine_permission="can_view_list")
def funcionario_detail_view(request, pk: uuid.UUID):
    """EXPEDIENTE CONTEXTUAL DE FUNCIONARIO (Workspace Principal)"""
    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    UserModel = get_user_model()
    funcionario = get_object_or_404(UserModel, id=pk)
    perfil = getattr(funcionario, "axentra_profile", None)

    raw_menu = AccountsPermissions.FUNCIONARIO_DETAIL_MENU
    detail_menu = []

    # Detectamos dinámicamente qué sub-vista se está solicitando o dejamos la de identidad por defecto
    current_sub_view = request.GET.get("sub_view", "accounts:funcionario_sub_identidad")

    for item in raw_menu:
        url_name = item.get("url_name")
        if not url_name:
            continue

        required_perm = item.get("permission")
        tiene_permiso = (
            request.axentra_is_root
            or required_perm in getattr(request, "axentra_permissions_list", [])
            or f"{AppIdentifier.ACCOUNTS}__{required_perm}" in getattr(request, "axentra_permissions_list", [])
        )

        if tiene_permiso:
            detail_menu.append({
                "icon": item.get("icon", "circle"),
                "title": item.get("title", "Sin título"),
                "href": reverse(url_name, args=[funcionario.id]),
                "order": item.get("order", 99),
                "provider": item.get("provider", AppIdentifier.ACCOUNTS),
                # Dinámico: Evalúa cuál está activa en la petición real
                "active": url_name == current_sub_view,
            })

    detail_menu.sort(key=lambda item: item["order"])

    context = {
        "funcionario": funcionario,
        "perfil": perfil,
        "current_funcionario": funcionario,
        "detail_menu": detail_menu,
        "modulo_actual": AppIdentifier.ACCOUNTS,
        "show_module_sidebar": True,
    }

    # Radar Forense Axentra
    if AxentraRadar.enabled():
        AxentraRadar.imprimir_auditoria(
            componente="accounts_view",
            request=request,
            titulo="Entrada a funcionario_detail_view",
            icono="🧬",
            extra_data={
                "Funcionario": funcionario.email,
                "Funcionario ID": str(funcionario.id),
                "¿Es petición HTMX?": is_htmx,
                "HX-Target": target_htmx if target_htmx else "F5 / URL directa",
                "Sidebar Contextual": True,
                "Items Contextuales": len(detail_menu),
                "Providers": ", ".join(sorted({item["provider"] for item in detail_menu})) if detail_menu else "Sin providers",
            },
        )

    if is_htmx and target_htmx == "workbench":
        return render(request, "accounts/workbench/funcionario_detail_workbench.html", context)

    return render(request, "accounts/pages/funcionario_detail.html", context)



@login_required
@axentra_module_gate(AppIdentifier.ACCOUNTS, required_fine_permission="can_create_user")
def funcionario_create_view(request):
    """
    CONTROLADOR DE ALTA DE FUNCIONARIOS

    Tipo de pantalla:
    - Pertenece al módulo ACCOUNTS.
    - No usa sidebar secundario.
    - Normalmente se carga dentro de #page-content.
    - En POST exitoso redirige al listado.
    """
    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    if AxentraRadar.enabled():
        AxentraRadar.imprimir_auditoria(
            componente="accounts_view",
            request=request,
            titulo="Entrada a funcionario_create_view",
            icono="🧾",
            extra_data={
                "Método": request.method,
                "¿Es petición HTMX?": is_htmx,
                "HX-Target Recibido": target_htmx if target_htmx else "NINGUNO",
                "HX-Current-URL": request.headers.get("HX-Current-URL", "N/A"),
            },
        )

    if request.method == "POST":
        datos_saneados = request.POST.copy()

        if "area" in datos_saneados and not datos_saneados["area"].strip():
            datos_saneados["area"] = ""

        form = StaffUserCreationForm(datos_saneados)
        profile_form = StaffUserProfileForm(datos_saneados)

        if form.is_valid() and profile_form.is_valid():
            area_instancia = profile_form.cleaned_data.get("area")

            payload = {
                "email": form.cleaned_data.get("email"),
                "first_name": form.cleaned_data.get("first_name"),
                "last_name": form.cleaned_data.get("last_name"),
                "phone": form.cleaned_data.get("phone"),
                "area_id": area_instancia.id if area_instancia else None,
                "puesto": profile_form.cleaned_data.get("puesto"),
                "telefono_oficina": profile_form.cleaned_data.get("telefono_oficina"),
            }

            exito, usuario, errores = FuncionarioService.crear_funcionario(
                request=request,
                post_data=payload,
                raw_password=form.cleaned_data.get("password"),
            )

            if exito and usuario:
                messages.success(
                    request,
                    f"El funcionario {usuario.full_name} ha sido dado de alta con éxito.",
                )

                if is_htmx:
                    response = HttpResponse(status=204)
                    response["HX-Redirect"] = reverse("accounts:funcionario_list")
                    return response

                return redirect("accounts:funcionario_list")

            if errores:
                form.add_error(None, _mensaje_legible(errores))

    else:
        form = StaffUserCreationForm()
        profile_form = StaffUserProfileForm()

    context = {
        "form": form,
        "profile_form": profile_form,

        # Contrato Axentra
        "modulo_actual": AppIdentifier.ACCOUNTS,
        "show_module_sidebar": False,
    }

    if AxentraRadar.enabled():
        AxentraRadar.imprimir_auditoria(
            componente="accounts_view",
            request=request,
            titulo="Despacho de Formulario de Alta",
            icono="📡",
            extra_data={
                "HX-Target": target_htmx if target_htmx else "F5 / URL directa",
                "Módulo": context["modulo_actual"],
                "Sidebar Secundario": context["show_module_sidebar"],
                "Errores Form": form.errors.as_data() if form.errors else "Sin errores",
                "Errores Profile Form": profile_form.errors.as_data() if profile_form.errors else "Sin errores",
            },
        )

    if is_htmx and target_htmx == "page-content":
        return render(
            request,
            "accounts/content/funcionario_create_form_content.html",
            context,
        )

    return render(
        request,
        "accounts/pages/funcionario_create.html",
        context,
    )

@login_required
@axentra_module_gate(AppIdentifier.ACCOUNTS, required_fine_permission="can_edit_user")
def funcionario_editar_view(request, pk: uuid.UUID):
    """Controlador de edición de funcionarios."""

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    usuario_instance = get_object_or_404(
        User,
        id=pk,
    )

    perfil_instance = get_object_or_404(
        UserProfile,
        user=usuario_instance,
    )

    if request.method == "POST":
        datos_saneados = request.POST.copy()

        if "area" in datos_saneados and not datos_saneados["area"].strip():
            datos_saneados["area"] = ""

        form_user = StaffUserChangeForm(
            datos_saneados,
            instance=usuario_instance,
        )

        form_profile = StaffUserProfileChangeForm(
            datos_saneados,
            instance=perfil_instance,
        )

        if form_user.is_valid() and form_profile.is_valid():
            area_instancia = form_profile.cleaned_data.get("area")

            payload = {
                "email": form_user.cleaned_data.get("email"),
                "first_name": form_user.cleaned_data.get("first_name"),
                "last_name": form_user.cleaned_data.get("last_name"),
                "phone": form_user.cleaned_data.get("phone"),
                "area_id": area_instancia.id if area_instancia else None,
                "puesto": form_profile.cleaned_data.get("puesto"),
                "telefono_oficina": form_profile.cleaned_data.get("telefono_oficina"),
            }

            exito, usuario, errores = FuncionarioService.editar_funcionario(
                request=request,
                pk=pk,
                post_data=payload,
            )

            if exito:
                messages.success(
                    request,
                    f"La ficha de {usuario.full_name} se actualizó correctamente.",
                )

                if is_htmx:
                    u_ref = get_object_or_404(
                        User,
                        id=pk,
                    )

                    p_ref = get_object_or_404(
                        UserProfile,
                        user=u_ref,
                    )

                    response = render(
                        request,
                        "accounts/htmx/funcionario_identidad_with_messages.html",
                        {
                            "funcionario": u_ref,
                            "perfil": p_ref,
                            "current_funcionario": u_ref,
                            "modulo_actual": AppIdentifier.ACCOUNTS,
                            "show_module_sidebar": True,
                        },
                    )

                    response["HX-Push-Url"] = reverse(
                        "accounts:funcionario_detail",
                        args=[pk],
                    )

                    return response

                return redirect(
                    "accounts:funcionario_detail",
                    pk=pk,
                )

            if errores:
                error_msg = _mensaje_legible(errores)

                messages.error(
                    request,
                    error_msg,
                )

                form_user.add_error(
                    None,
                    error_msg,
                )

        else:
            messages.error(
                request,
                "Revisa los campos del formulario antes de actualizar el funcionario.",
            )

    else:
        form_user = StaffUserChangeForm(
            instance=usuario_instance,
        )

        form_profile = StaffUserProfileChangeForm(
            instance=perfil_instance,
        )

    raw_menu = AccountsPermissions.FUNCIONARIO_DETAIL_MENU
    detail_menu = []

    for item in raw_menu:
        url_name = item.get("url_name")

        if not url_name:
            continue

        required_perm = item.get("permission")

        tiene_permiso = (
            getattr(request, "axentra_is_root", False)
            or required_perm in getattr(request, "axentra_permissions_list", [])
            or f"{AppIdentifier.ACCOUNTS}__{required_perm}" in getattr(request, "axentra_permissions_list", [])
        )

        if not tiene_permiso:
            continue

        detail_menu.append({
            "icon": item.get("icon", "circle"),
            "title": item.get("title", "Sin título"),
            "href": reverse(
                url_name,
                args=[usuario_instance.id],
            ),
            "order": item.get("order", 99),
            "provider": item.get("provider", AppIdentifier.ACCOUNTS),
            "active": url_name == "accounts:funcionario_sub_identidad",
        })

    detail_menu.sort(
        key=lambda item: item["order"],
    )

    context = {
        "form_user": form_user,
        "form_profile": form_profile,
        "funcionario": usuario_instance,
        "perfil": perfil_instance,
        "current_funcionario": usuario_instance,
        "detail_menu": detail_menu,
        "modulo_actual": AppIdentifier.ACCOUNTS,
        "show_module_sidebar": True,
    }

    if is_htmx and target_htmx == "page-content":
        return render(
            request,
            "accounts/htmx/funcionario_update_form_with_messages.html",
            context,
        )

    return render(
        request,
        "accounts/pages/funcionario_update.html",
        context,
    )

@login_required
@axentra_module_gate(AppIdentifier.ACCOUNTS, required_fine_permission="can_change_password")
def funcionario_cambiar_password_view(request, pk: uuid.UUID):
    """Controlador de rotación administrativa de contraseña para funcionarios."""

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    UserModel = get_user_model()

    usuario_instance = get_object_or_404(
        UserModel,
        id=pk,
    )

    perfil_instance = getattr(
        usuario_instance,
        "axentra_profile",
        None,
    )

    if request.method == "POST":
        form = SetPasswordForm(
            user=usuario_instance,
            data=request.POST,
        )

        if form.is_valid():
            nueva_password = form.cleaned_data.get("new_password1")

            success = FuncionarioService.forzar_reseteo_password(
                request=request,
                pk=pk,
                nueva_password=nueva_password,
            )

            if success:
                messages.success(
                    request,
                    f"Credenciales restablecidas con éxito para {usuario_instance.full_name}.",
                )

                if is_htmx:
                    usuario_refrescado = get_object_or_404(
                        UserModel,
                        id=pk,
                    )

                    perfil_refrescado = getattr(
                        usuario_refrescado,
                        "axentra_profile",
                        None,
                    )

                    response = render(
                        request,
                        "accounts/htmx/funcionario_identidad_with_messages.html",
                        {
                            "funcionario": usuario_refrescado,
                            "perfil": perfil_refrescado,
                            "current_funcionario": usuario_refrescado,
                            "modulo_actual": AppIdentifier.ACCOUNTS,
                            "show_module_sidebar": True,
                        },
                    )

                    response["HX-Push-Url"] = reverse(
                        "accounts:funcionario_detail",
                        args=[pk],
                    )

                    return response

                return redirect(
                    "accounts:funcionario_detail",
                    pk=pk,
                )

            messages.error(
                request,
                "No se pudo restablecer la credencial en el Core.",
            )

        else:
            messages.error(
                request,
                "Revisa los campos del formulario antes de restablecer la contraseña.",
            )

    else:
        form = SetPasswordForm(
            user=usuario_instance,
        )

    raw_menu = AccountsPermissions.FUNCIONARIO_DETAIL_MENU
    detail_menu = []

    for item in raw_menu:
        url_name = item.get("url_name")

        if not url_name:
            continue

        required_perm = item.get("permission")

        tiene_permiso = (
            getattr(request, "axentra_is_root", False)
            or required_perm in getattr(request, "axentra_permissions_list", [])
            or f"{AppIdentifier.ACCOUNTS}__{required_perm}" in getattr(request, "axentra_permissions_list", [])
        )

        if not tiene_permiso:
            continue

        detail_menu.append({
            "icon": item.get("icon", "circle"),
            "title": item.get("title", "Sin título"),
            "href": reverse(
                url_name,
                args=[usuario_instance.id],
            ),
            "order": item.get("order", 99),
            "provider": item.get("provider", AppIdentifier.ACCOUNTS),
            "active": url_name == "accounts:funcionario_sub_identidad",
        })

    detail_menu.sort(
        key=lambda item: item["order"],
    )

    context = {
        "form": form,
        "funcionario": usuario_instance,
        "perfil": perfil_instance,
        "current_funcionario": usuario_instance,
        "detail_menu": detail_menu,
        "modulo_actual": AppIdentifier.ACCOUNTS,
        "show_module_sidebar": True,
    }

    if is_htmx and target_htmx == "page-content":
        return render(
            request,
            "accounts/htmx/funcionario_password_form_with_messages.html",
            context,
        )

    return render(
        request,
        "accounts/pages/funcionario_password.html",
        context,
    )

@require_POST
@login_required
@axentra_module_gate(AppIdentifier.ACCOUNTS, required_fine_permission="can_delete_user")
def funcionario_soft_delete_view(request, pk: uuid.UUID):
    """
    Baja lógica institucional de funcionario.

    - No permite baja sobre la propia sesión.
    - Si es exitosa, regresa al listado oficial.
    - En HTMX incluye messages_oob para mostrar toast sin F5.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"

    if str(pk) == str(request.user.id):
        messages.error(
            request,
            "Operación denegada: No puede aplicar una baja sobre su propia sesión.",
        )

        if is_htmx:
            funcionario = get_object_or_404(
                User,
                id=pk,
            )

            perfil = getattr(
                funcionario,
                "axentra_profile",
                None,
            )

            response = render(
                request,
                "accounts/htmx/funcionario_identidad_with_messages.html",
                {
                    "funcionario": funcionario,
                    "perfil": perfil,
                    "current_funcionario": funcionario,
                    "modulo_actual": AppIdentifier.ACCOUNTS,
                    "show_module_sidebar": True,
                },
            )

            response.status_code = 403
            return response

        return redirect(
            "accounts:funcionario_detail",
            pk=pk,
        )

    funcionario = get_object_or_404(
        User,
        id=pk,
    )

    exito, mensaje = FuncionarioService.tramitar_baja_institucional(
        request=request,
        pk=pk,
        operador_email=request.user.email,
    )

    if exito:
        messages.warning(
            request,
            mensaje,
        )
    else:
        messages.error(
            request,
            mensaje,
        )

    if is_htmx:
        context_list = build_funcionario_list_context(request)

        response = render(
            request,
            "accounts/htmx/funcionario_list_workbench_with_messages.html",
            context_list,
        )

        response["HX-Push-Url"] = reverse(
            "accounts:funcionario_list",
        )

        return response

    return redirect(
        "accounts:funcionario_list",
    )


@require_POST
@login_required
@axentra_module_gate(AppIdentifier.ACCOUNTS, required_fine_permission="can_edit_user")
def funcionario_toggle_status_view(request, pk: uuid.UUID):
    """
    Alternador de estatus operativo de funcionario.

    - Si viene desde expediente con hx-target="#page-content":
      devuelve la ficha de identidad completa con messages_oob.

    - Si viene desde badge compacto:
      devuelve el badge con messages_oob.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    funcionario = get_object_or_404(
        User,
        id=pk,
    )

    perfil = getattr(
        funcionario,
        "axentra_profile",
        None,
    )

    if str(pk) == str(request.user.id):
        messages.error(
            request,
            "Bloqueo de seguridad: no puedes cambiar el estado de tu propia cuenta.",
        )

        if is_htmx and target_htmx == "page-content":
            response = render(
                request,
                "accounts/htmx/funcionario_identidad_with_messages.html",
                {
                    "funcionario": funcionario,
                    "perfil": perfil,
                    "current_funcionario": funcionario,
                    "modulo_actual": AppIdentifier.ACCOUNTS,
                    "show_module_sidebar": True,
                },
            )
            response.status_code = 403
            return response

        if is_htmx:
            response = render(
                request,
                "common/tags/badge_toggle_with_messages.html",
                {
                    "is_active": funcionario.is_active,
                    "toggle_url": reverse(
                        "accounts:funcionario_toggle_status",
                        args=[funcionario.id],
                    ),
                },
            )
            response.status_code = 403
            return response

        return redirect(
            "accounts:funcionario_detail",
            pk=pk,
        )

    if funcionario.is_deleted:
        messages.error(
            request,
            "No se puede cambiar el estado de un usuario dado de baja.",
        )

        if is_htmx and target_htmx == "page-content":
            response = render(
                request,
                "accounts/htmx/funcionario_identidad_with_messages.html",
                {
                    "funcionario": funcionario,
                    "perfil": perfil,
                    "current_funcionario": funcionario,
                    "modulo_actual": AppIdentifier.ACCOUNTS,
                    "show_module_sidebar": True,
                },
            )
            response.status_code = 400
            return response

        if is_htmx:
            response = render(
                request,
                "common/tags/badge_toggle_with_messages.html",
                {
                    "is_active": funcionario.is_active,
                    "toggle_url": reverse(
                        "accounts:funcionario_toggle_status",
                        args=[funcionario.id],
                    ),
                },
            )
            response.status_code = 400
            return response

        return redirect(
            "accounts:funcionario_detail",
            pk=pk,
        )

    funcionario.is_active = not funcionario.is_active
    funcionario.save(
        update_fields=[
            "is_active",
        ]
    )

    if funcionario.is_active:
        messages.success(
            request,
            f"La cuenta de {funcionario.full_name} fue activada correctamente.",
        )
    else:
        messages.warning(
            request,
            f"La cuenta de {funcionario.full_name} fue desactivada correctamente.",
        )

    perfil = getattr(
        funcionario,
        "axentra_profile",
        None,
    )

    if is_htmx and target_htmx == "page-content":
        response = render(
            request,
            "accounts/htmx/funcionario_identidad_with_messages.html",
            {
                "funcionario": funcionario,
                "perfil": perfil,
                "current_funcionario": funcionario,
                "modulo_actual": AppIdentifier.ACCOUNTS,
                "show_module_sidebar": True,
            },
        )

        response["HX-Push-Url"] = reverse(
            "accounts:funcionario_detail",
            args=[funcionario.id],
        )

        return response

    if is_htmx:
        return render(
            request,
            "common/tags/badge_toggle_with_messages.html",
            {
                "is_active": funcionario.is_active,
                "toggle_url": reverse(
                    "accounts:funcionario_toggle_status",
                    args=[funcionario.id],
                ),
            },
        )

    return redirect(
        "accounts:funcionario_detail",
        pk=pk,
    )



@login_required
@axentra_module_gate(AppIdentifier.ACCOUNTS, required_fine_permission="can_view_list")
def funcionario_sub_identidad_view(request, pk: uuid.UUID):
    funcionario = get_object_or_404(User, id=pk)
    perfil = getattr(funcionario, "axentra_profile", None)

    return render(
        request,
        "accounts/contextual/partials/sub_identidad.html",
        {
            "funcionario": funcionario,
            "perfil": perfil,
            "modulo_actual": AppIdentifier.ACCOUNTS,
            "show_module_sidebar": True,
        },
    )
