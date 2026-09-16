# apps/security/views/security_views.py
import json
import logging
from urllib.parse import urlencode
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.security.models.organigrama import AppDependencyCapability, AreaOperativa, Dependencia, Sede
from apps.shared.apps_config import AppIdentifier
from apps.security.decorators import axentra_module_gate
from apps.security.models import AppModule, UserAppRole, TenantConfig, SecurityAuditLog
from apps.security.forms import TenantConfigForm, PrivacidadCookiesForm
from apps.security.selectors.application_selectors import ApplicationGovernanceSelectors
from apps.security.selectors.permission_selectors import PermissionSelectors
from apps.security.selectors.security_selectors import CapabilitySelectors, SecurityDashboardSelectors
from apps.security.services.security_services import PermissionService
from apps.security.utils.forensic_auditor import ForensicAuditor

User = get_user_model()
logger = logging.getLogger(__name__)


@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="has_access_module")
def security_control_panel_view(request):
    """
    Cockpit central del módulo Security.

    - is_manager ve gobierno global.
    - owner de app ve sólo las apps bajo su gobierno.
    - Click desde sidebar global reemplaza #workbench.
    - Navegación interna reemplaza #page-content.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    es_platform_manager = (
        getattr(request, "axentra_is_root", False)
        or getattr(request.user, "is_manager", False)
    )

    context = {
        "modulo_actual": AppIdentifier.SECURITY,
        "show_module_sidebar": True,
        "current_security_view": "security:control_panel",
        "es_platform_manager": es_platform_manager,
        **ApplicationGovernanceSelectors.overview(request.user),
    }

    if is_htmx and target_htmx == "workbench":
        return render(
            request,
            "security/workbench/control_panel_workbench.html",
            context,
        )

    if is_htmx and target_htmx == "page-content":
        return render(
            request,
            "security/content/control_panel_content.html",
            context,
        )

    return render(
        request,
        "security/pages/control_panel.html",
        context,
    )
    

@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="has_access_module")
def security_applications_view(request):
    """Catálogo paginado limitado al alcance del administrador autenticado."""
    query = request.GET.get("q", "").strip()[:100]
    owner = request.GET.get("owner", "")
    if owner not in ("with", "without"):
        owner = ""
    ordering = request.GET.get("sort", "name")
    if ordering not in ("name", "-name", "-total_usuarios"):
        ordering = "name"
    apps = ApplicationGovernanceSelectors.with_counts(
        ApplicationGovernanceSelectors.scope(request.user)
    )
    if query:
        apps = apps.filter(Q(name__icontains=query) | Q(slug__icontains=query))
    if owner == "without":
        apps = apps.filter(total_owners=0)
    elif owner == "with":
        apps = apps.filter(total_owners__gt=0)
    page = Paginator(apps.order_by(ordering, "pk"), 20).get_page(request.GET.get("page"))
    context = {
        "modulo_actual": AppIdentifier.SECURITY,
        "show_module_sidebar": True,
        "current_security_view": "security:applications",
        "page_obj": page, "q": query, "owner_filter": owner, "sort": ordering,
        "filter_query": urlencode({"q": query, "owner": owner, "sort": ordering}),
    }
    target = request.headers.get("HX-Target", "")
    htmx = request.headers.get("HX-Request", "").lower() == "true"
    if htmx and target == "page-content":
        template = "security/content/applications_content.html"
    elif htmx and target == "workbench":
        template = "security/workbench/applications_workbench.html"
    else:
        template = "security/pages/applications.html"
    return render(request, template, context)


@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="can_view_analytics")
def security_dashboard_view(request):
    """
    Consola Central de Ciberseguridad.

    - Vista completa: shell/workbench.
    - Navegación interna Security: #page-content.
    - Filtros GET: recargan la misma vista.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    filtros = {
        "app_namespace": request.GET.get("app_namespace", "").strip().lower() or None,
        "action_type": request.GET.get("action_type", "").strip().upper() or None,
        "level_status": request.GET.get("level_status", "").strip().upper() or None,
        "search_target": request.GET.get("search_target", "").strip() or None,
        "operador": request.GET.get("operador", "").strip().lower() or None,
        "fecha_inicio": request.GET.get("fecha_inicio", "").strip() or None,
        "fecha_fin": request.GET.get("fecha_fin", "").strip() or None,
    }

    context = SecurityDashboardSelectors.obtener_metricas_firewall()

    context["recents_audits"] = SecurityDashboardSelectors.obtener_buffer_auditoria(
        limite=50,
        filtros=filtros,
    )

    log_counts = (
        SecurityAuditLog.objects
        .values("app_namespace")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )

    g_logs_labels = [
        item["app_namespace"].upper()
        for item in log_counts
        if item["app_namespace"]
    ]

    g_logs_valores = [
        item["total"]
        for item in log_counts
        if item["app_namespace"]
    ]

    level_counts = (
        SecurityAuditLog.objects
        .values("level_status")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    g_levels_labels = [
        item["level_status"]
        for item in level_counts
        if item["level_status"]
    ]

    g_levels_valores = [
        item["total"]
        for item in level_counts
        if item["level_status"]
    ]

    context.update({
        "apps_sistema": [
            choice[0]
            for choice in AppIdentifier.get_choices()
        ],
        "tipos_accion": SecurityAuditLog.ActionTypes.choices,
        "niveles_status": SecurityAuditLog.Levels.choices,
        "filtros_actuales": filtros,

        "g_logs_labels": json.dumps(g_logs_labels),
        "g_logs_valores": json.dumps(g_logs_valores),
        "g_levels_labels": json.dumps(g_levels_labels),
        "g_levels_valores": json.dumps(g_levels_valores),

        "modulo_actual": AppIdentifier.SECURITY,
        "show_module_sidebar": True,
        "current_security_view": "security:dashboard",
    })

    if is_htmx and target_htmx == "workbench":
        return render(
            request,
            "security/workbench/security_dashboard_workbench.html",
            context,
        )

    if is_htmx and target_htmx == "page-content":
        return render(
            request,
            "security/content/security_dashboard_content.html",
            context,
        )

    return render(
        request,
        "security/pages/security_dashboard.html",
        context,
    )


@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="can_view_matrix")
def dynamic_permission_matrix_view(request):
    """
    Matriz dinámica de permisos por aplicación.

    Regla:
    - La matriz siempre requiere app_slug explícito.
    - No existe matriz global editable sin contexto de aplicación.
    - is_manager/root puede abrir cualquier app.
    - owner sólo puede abrir apps donde tiene gobierno delegado.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    app_slug = request.GET.get("app_slug", "").strip().lower()
    user_focus_id = request.GET.get("user_id")

    es_platform_manager = (
        getattr(request, "axentra_is_root", False)
        or getattr(request.user, "is_manager", False)
        or (
            hasattr(request.user, "axentra_profile")
            and getattr(request.user.axentra_profile, "is_root_admin", False)
        )
    )

    if es_platform_manager:
        apps_gobernadas = list(
            AppModule.objects
            .filter(
                is_active=True,
                is_deleted=False,
            )
            .order_by("name")
        )
    else:
        roles_owner = (
            UserAppRole.objects
            .filter(
                user=request.user,
                role=UserAppRole.ReservedRoles.OWNER,
                is_active=True,
                is_deleted=False,
                app__is_active=True,
                app__is_deleted=False,
            )
            .select_related("app")
            .order_by("app__name")
        )

        apps_gobernadas = [
            rol.app
            for rol in roles_owner
            if rol.app
        ]

    if not app_slug:
        messages.error(
            request,
            "Acceso denegado: la matriz de permisos requiere una aplicación explícita.",
        )

        context_denied = {
            "modulo_actual": AppIdentifier.SECURITY,
            "show_module_sidebar": True,
            "current_security_view": "security:dynamic_matrix",
            "apps_gobernadas": apps_gobernadas,
            "app": None,
            "app_slug_actual": "",
            "user_focus_id": None,
            "es_platform_manager": es_platform_manager,
            "personal_list": [],
            "usuarios_potenciales": [],
            "mostrar_buscador": False,
            "roles_choices": [],
            "role_mapping_json": "{}",
            "roles_buscador": [],
            "usuario_enfocado": None,
            "error_detalle": "La matriz requiere app_slug. Regresa al Cockpit y selecciona una aplicación.",
        }

        if is_htmx and target_htmx == "workbench":
            response = render(
                request,
                "security/workbench/permission_matrix_workbench.html",
                context_denied,
                status=403,
            )
            return response

        if is_htmx and target_htmx == "page-content":
            response = render(
                request,
                "security/htmx/permission_matrix_with_messages.html",
                context_denied,
                status=403,
            )
            return response

        return render(
            request,
            "security/pages/permission_matrix.html",
            context_denied,
            status=403,
        )

    app_module = get_object_or_404(
        AppModule,
        slug=app_slug,
        is_active=True,
        is_deleted=False,
    )

    if not es_platform_manager:
        tiene_gobierno_sobre_app = any(
            app.id == app_module.id
            for app in apps_gobernadas
        )

        if not tiene_gobierno_sobre_app:
            messages.error(
                request,
                "Acceso denegado: no tienes gobierno delegado sobre esta aplicación.",
            )

            context_denied = {
                "modulo_actual": AppIdentifier.SECURITY,
                "show_module_sidebar": True,
                "current_security_view": "security:dynamic_matrix",
                "apps_gobernadas": apps_gobernadas,
                "app": None,
                "app_slug_actual": "",
                "user_focus_id": None,
                "es_platform_manager": es_platform_manager,
                "personal_list": [],
                "usuarios_potenciales": [],
                "mostrar_buscador": False,
                "roles_choices": [],
                "role_mapping_json": "{}",
                "roles_buscador": [],
                "usuario_enfocado": None,
                "error_detalle": "No tienes permisos para administrar esta aplicación.",
            }

            if is_htmx and target_htmx == "page-content":
                response = render(
                    request,
                    "security/htmx/permission_matrix_with_messages.html",
                    context_denied,
                    status=403,
                )
                return response

            return render(
                request,
                "security/pages/permission_matrix.html",
                context_denied,
                status=403,
            )

    context = build_permission_matrix_context(
        request=request,
        app_module=app_module,
        user_focus_id=user_focus_id,
        es_platform_manager=es_platform_manager,
    )

    if is_htmx and target_htmx == "workbench":
        return render(
            request,
            "security/workbench/permission_matrix_workbench.html",
            context,
        )

    if is_htmx and target_htmx == "page-content":
        return render(
            request,
            "security/content/permission_matrix_content.html",
            context,
        )

    if is_htmx and target_htmx == "panel-permisos":
        return render(
            request,
            "security/partials/matrix_form_partial.html",
            context,
        )

    return render(
        request,
        "security/pages/permission_matrix.html",
        context,
    )


@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="can_modify_matrix")
@require_POST
def guardar_llaves_json_view(request, app_id, user_id):
    """
    Persistencia de llaves JSON/permisos finos para usuario dentro de una app.

    - Normal: guarda y redirige a la matriz enfocada.
    - HTMX: guarda, repinta la matriz con messages_oob y actualiza URL.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"

    app_module = get_object_or_404(
        AppModule,
        id=app_id,
        is_active=True,
        is_deleted=False,
    )

    target_user = get_object_or_404(
        User,
        id=user_id,
    )

    is_manager_global = (
        getattr(request, "axentra_is_root", False)
        or getattr(request.user, "is_manager", False)
        or (
            hasattr(request.user, "axentra_profile")
            and getattr(request.user.axentra_profile, "is_root_admin", False)
        )
    )

    if not is_manager_global:
        es_owner_de_app = UserAppRole.objects.filter(
            user=request.user,
            app=app_module,
            role=UserAppRole.ReservedRoles.OWNER,
            is_active=True,
            is_deleted=False,
        ).exists()

        if not es_owner_de_app:
            messages.error(
                request,
                "No tienes gobierno delegado sobre esta aplicación.",
            )

            if is_htmx:
                context = build_permission_matrix_context(
                    request=request,
                    app_module=app_module,
                    user_focus_id=target_user.id,
                    es_platform_manager=is_manager_global,
                )

                response = render(
                    request,
                    "security/htmx/permission_matrix_with_messages.html",
                    context,
                    status=403,
                )

                response["HX-Push-Url"] = (
                    reverse("security:dynamic_matrix")
                    + f"?app_slug={app_module.slug}&user_id={target_user.id}"
                )

                return response

            return redirect(
                reverse("security:dynamic_matrix")
                + f"?app_slug={app_module.slug}&user_id={target_user.id}"
            )

    nuevo_rol = (
        request.POST.get("role")
        or request.POST.get(f"role_{user_id}")
        or request.POST.get("nuevo_rol")
    )

    if not nuevo_rol:
        messages.error(
            request,
            "No se especificó un rol válido en la petición.",
        )

        if is_htmx:
            context = build_permission_matrix_context(
                request=request,
                app_module=app_module,
                user_focus_id=target_user.id,
                es_platform_manager=is_manager_global,
            )

            response = render(
                request,
                "security/htmx/permission_matrix_with_messages.html",
                context,
                status=400,
            )

            response["HX-Push-Url"] = (
                reverse("security:dynamic_matrix")
                + f"?app_slug={app_module.slug}&user_id={target_user.id}"
            )

            return response

        return redirect(
            reverse("security:dynamic_matrix")
            + f"?app_slug={app_module.slug}&user_id={target_user.id}"
        )

    llaves_encendidas = (
        request.POST.getlist("permisos_checks")
        or request.POST.getlist(f"user_{user_id}")
        or []
    )

    exito, mensaje = PermissionService.save_matrix_permissions(
        request=request,
        target_user=target_user,
        app_module=app_module,
        nuevo_rol=nuevo_rol,
        llaves_encendidas=llaves_encendidas,
        is_manager_bypass=is_manager_global,
    )

    if exito:
        messages.success(
            request,
            mensaje,
        )
    else:
        messages.error(
            request,
            mensaje,
        )

    if is_htmx:
        context = build_permission_matrix_context(
            request=request,
            app_module=app_module,
            user_focus_id=target_user.id,
            es_platform_manager=is_manager_global,
        )

        response = render(
            request,
            "security/htmx/permission_matrix_with_messages.html",
            context,
        )

        response["HX-Push-Url"] = (
            reverse("security:dynamic_matrix")
            + f"?app_slug={app_module.slug}&user_id={target_user.id}"
        )

        return response

    return redirect(
        reverse("security:dynamic_matrix")
        + f"?app_slug={app_module.slug}&user_id={target_user.id}"
    )

def build_permission_matrix_context(
    request,
    app_module: AppModule | None = None,
    user_focus_id=None,
    es_platform_manager: bool | None = None,
):
    """
    Construye el contexto oficial de la matriz de permisos.

    Debe usarse por:
    - dynamic_permission_matrix_view
    - guardar_llaves_json_view
    - inyectar_funcionario_view
    - toggle_user_modulo_active_ajax_view
    - expulsar_usuario_modulo_total_ajax_view
    """

    if es_platform_manager is None:
        es_platform_manager = (
            getattr(request, "axentra_is_root", False)
            or getattr(request.user, "is_manager", False)
            or (
                hasattr(request.user, "axentra_profile")
                and getattr(request.user.axentra_profile, "is_root_admin", False)
            )
        )

    if es_platform_manager:
        apps_gobernadas = list(
            AppModule.objects
            .filter(
                is_active=True,
                is_deleted=False,
            )
            .order_by("name")
        )
    else:
        roles_owner = (
            UserAppRole.objects
            .filter(
                user=request.user,
                role=UserAppRole.ReservedRoles.OWNER,
                is_active=True,
                is_deleted=False,
                app__is_active=True,
                app__is_deleted=False,
            )
            .select_related("app")
            .order_by("app__name")
        )

        apps_gobernadas = [
            rol.app
            for rol in roles_owner
            if rol.app
        ]

    if not app_module and apps_gobernadas:
        app_module = apps_gobernadas[0]

    matrix_context = {}

    if app_module:
        matrix_context = PermissionSelectors.get_secured_matrix_data(
            app_module=app_module,
            user_focus_id=user_focus_id,
            request_user=request.user,
            is_manager_global=es_platform_manager,
        ) or {}

    role_mapping = matrix_context.get("role_mapping") or {}
    roles_choices = matrix_context.get("roles_choices") or []

    context = {
        "modulo_actual": AppIdentifier.SECURITY,
        "show_module_sidebar": True,
        "current_security_view": "security:dynamic_matrix",

        "apps_gobernadas": apps_gobernadas,
        "app": app_module,
        "app_slug_actual": app_module.slug if app_module else "",
        "user_focus_id": user_focus_id,
        "es_platform_manager": es_platform_manager,

        "role_mapping_json": json.dumps(role_mapping),
        "roles_buscador": [
            rol[0]
            for rol in roles_choices
        ],

        "personal_list": matrix_context.get("personal_list", []),
        "usuarios_potenciales": matrix_context.get("usuarios_potenciales", []),
        "mostrar_buscador": matrix_context.get("mostrar_buscador", False),
        "roles_choices": roles_choices,
        "usuario_enfocado": matrix_context.get("usuario_enfocado"),
    }

    context.update(matrix_context)

    return context



@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="can_modify_matrix")
@require_POST
def inyectar_funcionario_view(request, app_id):
    """
    Inyecta un funcionario al padrón de membresía de una app.

    - is_manager/root puede inyectar en cualquier app.
    - owner puede inyectar sólo en sus apps.
    - Sólo is_manager/root puede inyectar rol owner.
    - En HTMX repinta la matriz con messages_oob.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"

    app_module = get_object_or_404(
        AppModule,
        id=app_id,
        is_active=True,
        is_deleted=False,
    )

    is_manager_global = (
        getattr(request, "axentra_is_root", False)
        or getattr(request.user, "is_manager", False)
        or (
            hasattr(request.user, "axentra_profile")
            and getattr(request.user.axentra_profile, "is_root_admin", False)
        )
    )

    if not is_manager_global:
        es_owner_de_app = UserAppRole.objects.filter(
            user=request.user,
            app=app_module,
            role=UserAppRole.ReservedRoles.OWNER,
            is_active=True,
            is_deleted=False,
        ).exists()

        if not es_owner_de_app:
            messages.error(
                request,
                "Acceso denegado: no tienes gobierno delegado sobre esta aplicación.",
            )

            if is_htmx:
                context = build_permission_matrix_context(
                    request=request,
                    app_module=app_module,
                    user_focus_id=None,
                    es_platform_manager=is_manager_global,
                )

                response = render(
                    request,
                    "security/htmx/permission_matrix_with_messages.html",
                    context,
                    status=403,
                )

                response["HX-Push-Url"] = (
                    reverse("security:dynamic_matrix")
                    + f"?app_slug={app_module.slug}"
                )

                return response

            return redirect(
                reverse("security:dynamic_matrix")
                + f"?app_slug={app_module.slug}"
            )

    nuevo_usuario_id = request.POST.get("new_user_id")
    rol_a_inyectar = request.POST.get("initial_role", UserAppRole.ReservedRoles.VIEWER)

    if not nuevo_usuario_id:
        messages.error(
            request,
            "Debes seleccionar un funcionario válido para inyectarlo al módulo.",
        )

        if is_htmx:
            context = build_permission_matrix_context(
                request=request,
                app_module=app_module,
                user_focus_id=None,
                es_platform_manager=is_manager_global,
            )

            response = render(
                request,
                "security/htmx/permission_matrix_with_messages.html",
                context,
                status=400,
            )

            response["HX-Push-Url"] = (
                reverse("security:dynamic_matrix")
                + f"?app_slug={app_module.slug}"
            )

            return response

        return redirect(
            reverse("security:dynamic_matrix")
            + f"?app_slug={app_module.slug}"
        )

    target_user = get_object_or_404(
        User,
        id=nuevo_usuario_id,
        is_deleted=False,
    )

    if (
        rol_a_inyectar == UserAppRole.ReservedRoles.OWNER
        and not is_manager_global
    ):
        messages.error(
            request,
            "Sólo un administrador global puede asignar rol owner.",
        )

        if is_htmx:
            context = build_permission_matrix_context(
                request=request,
                app_module=app_module,
                user_focus_id=target_user.id,
                es_platform_manager=is_manager_global,
            )

            response = render(
                request,
                "security/htmx/permission_matrix_with_messages.html",
                context,
                status=403,
            )

            response["HX-Push-Url"] = (
                reverse("security:dynamic_matrix")
                + f"?app_slug={app_module.slug}&user_id={target_user.id}"
            )

            return response

        return redirect(
            reverse("security:dynamic_matrix")
            + f"?app_slug={app_module.slug}&user_id={target_user.id}"
        )

    operacion_exitosa = PermissionService.authorize_new_user_entry(
        request,
        app_module,
        str(target_user.id),
        rol_a_inyectar,
    )

    if operacion_exitosa:
        messages.success(
            request,
            f"Funcionario {target_user.email} inyectado correctamente en {app_module.name}.",
        )
    else:
        messages.warning(
            request,
            "Operación cancelada: el funcionario ya cuenta con membresía activa en esta aplicación.",
        )

    if is_htmx:
        context = build_permission_matrix_context(
            request=request,
            app_module=app_module,
            user_focus_id=target_user.id,
            es_platform_manager=is_manager_global,
        )

        response = render(
            request,
            "security/htmx/permission_matrix_with_messages.html",
            context,
        )

        response["HX-Push-Url"] = (
            reverse("security:dynamic_matrix")
            + f"?app_slug={app_module.slug}&user_id={target_user.id}"
        )

        return response

    return redirect(
        reverse("security:dynamic_matrix")
        + f"?app_slug={app_module.slug}&user_id={target_user.id}"
    )


@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="can_modify_matrix")
@require_POST
def toggle_user_modulo_active_ajax_view(request, user_id, app_id):
    """
    Conmuta el estado activo/suspendido de un funcionario dentro de una app.

    - No permite auto-suspensión.
    - Owner sólo puede ser suspendido/reactivado por manager/root.
    - En HTMX repinta la matriz con messages_oob.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"

    app_module = get_object_or_404(
        AppModule,
        id=app_id,
        is_active=True,
        is_deleted=False,
    )

    target_user = get_object_or_404(
        User,
        id=user_id,
        is_deleted=False,
    )

    is_manager_global = (
        getattr(request, "axentra_is_root", False)
        or getattr(request.user, "is_manager", False)
        or getattr(request.user, "is_superuser", False)
        or (
            hasattr(request.user, "axentra_profile")
            and getattr(request.user.axentra_profile, "is_root_admin", False)
        )
    )

    matriz_url = (
        reverse("security:dynamic_matrix")
        + f"?app_slug={app_module.slug}&user_id={target_user.id}"
    )

    if str(target_user.id) == str(request.user.id):
        messages.error(
            request,
            "Operación denegada: no puedes suspender tu propia membresía.",
        )

        if is_htmx:
            context = build_permission_matrix_context(
                request=request,
                app_module=app_module,
                user_focus_id=target_user.id,
                es_platform_manager=is_manager_global,
            )

            response = render(
                request,
                "security/htmx/permission_matrix_with_messages.html",
                context,
                status=403,
            )

            response["HX-Push-Url"] = matriz_url
            return response

        return redirect(matriz_url)

    rol_instancia = get_object_or_404(
        UserAppRole,
        user=target_user,
        app=app_module,
        is_deleted=False,
    )

    if rol_instancia.role.lower() == "owner" and not is_manager_global:
        messages.error(
            request,
            "Acceso denegado: el rol owner está protegido por jerarquía superior.",
        )

        if is_htmx:
            context = build_permission_matrix_context(
                request=request,
                app_module=app_module,
                user_focus_id=target_user.id,
                es_platform_manager=is_manager_global,
            )

            response = render(
                request,
                "security/htmx/permission_matrix_with_messages.html",
                context,
                status=403,
            )

            response["HX-Push-Url"] = matriz_url
            return response

        return redirect(matriz_url)

    rol_instancia.is_active = not rol_instancia.is_active
    rol_instancia.save(
        update_fields=[
            "is_active",
            "updated_at",
        ]
    )

    ForensicAuditor.registrar_evento(
        request=request,
        action_type=SecurityAuditLog.ActionTypes.RESET,
        module_component="ESTADO_MEMBRESIA",
        action_name="TOGGLE_SUSPENSION_MODULO",
        target_scope=(
            f"Conmutación de membresía para {target_user.email} "
            f"en {app_module.name} "
            f"(Estado: {rol_instancia.is_active})."
        ),
        level=(
            SecurityAuditLog.Levels.INFO
            if rol_instancia.is_active
            else SecurityAuditLog.Levels.CRITICAL
        ),
        target_user=target_user,
        search_target=str(target_user.id),
        payload={
            "is_active_final": rol_instancia.is_active,
            "app_id": str(app_module.id),
            "app_slug": app_module.slug,
            "role": rol_instancia.role,
            "operador_id": str(request.user.id),
            "operador_email": request.user.email,
        },
    )

    if rol_instancia.is_active:
        messages.success(
            request,
            f"La membresía de {target_user.email} fue reactivada en {app_module.name}.",
        )
    else:
        messages.warning(
            request,
            f"La membresía de {target_user.email} fue suspendida en {app_module.name}.",
        )

    if is_htmx:
        context = build_permission_matrix_context(
            request=request,
            app_module=app_module,
            user_focus_id=target_user.id,
            es_platform_manager=is_manager_global,
        )

        response = render(
            request,
            "security/htmx/permission_matrix_with_messages.html",
            context,
        )

        response["HX-Push-Url"] = matriz_url
        return response

    return redirect(matriz_url)


@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="can_modify_matrix")
@require_POST
def expulsar_usuario_modulo_total_ajax_view(request, user_id, app_id):
    """
    Purga total de membresía de un usuario dentro de una app.

    - Sólo manager/root puede purgar membresías.
    - No permite auto-purga.
    - Elimina la membresía UserAppRole.
    - En HTMX repinta la matriz con messages_oob.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"

    app_module = get_object_or_404(
        AppModule,
        id=app_id,
        is_active=True,
        is_deleted=False,
    )

    target_user = get_object_or_404(
        User,
        id=user_id,
        is_deleted=False,
    )

    is_manager_global = (
        getattr(request, "axentra_is_root", False)
        or getattr(request.user, "is_manager", False)
        or getattr(request.user, "is_superuser", False)
        or (
            hasattr(request.user, "axentra_profile")
            and getattr(request.user.axentra_profile, "is_root_admin", False)
        )
    )

    matriz_url = (
        reverse("security:dynamic_matrix")
        + f"?app_slug={app_module.slug}"
    )

    matriz_url_con_usuario = (
        reverse("security:dynamic_matrix")
        + f"?app_slug={app_module.slug}&user_id={target_user.id}"
    )

    if not is_manager_global:
        messages.error(
            request,
            "Acceso denegado: la purga total requiere nivel manager/root.",
        )

        if is_htmx:
            context = build_permission_matrix_context(
                request=request,
                app_module=app_module,
                user_focus_id=target_user.id,
                es_platform_manager=is_manager_global,
            )

            response = render(
                request,
                "security/htmx/permission_matrix_with_messages.html",
                context,
                status=403,
            )

            response["HX-Push-Url"] = matriz_url_con_usuario
            return response

        return redirect(matriz_url_con_usuario)

    if str(target_user.id) == str(request.user.id):
        messages.error(
            request,
            "Operación denegada: no puedes purgar tu propia membresía.",
        )

        if is_htmx:
            context = build_permission_matrix_context(
                request=request,
                app_module=app_module,
                user_focus_id=target_user.id,
                es_platform_manager=is_manager_global,
            )

            response = render(
                request,
                "security/htmx/permission_matrix_with_messages.html",
                context,
                status=403,
            )

            response["HX-Push-Url"] = matriz_url_con_usuario
            return response

        return redirect(matriz_url_con_usuario)

    rol_instancia = (
        UserAppRole.objects
        .filter(
            user=target_user,
            app=app_module,
            is_deleted=False,
        )
        .first()
    )

    if not rol_instancia:
        messages.warning(
            request,
            f"{target_user.email} no tiene membresía registrada en {app_module.name}.",
        )

        if is_htmx:
            context = build_permission_matrix_context(
                request=request,
                app_module=app_module,
                user_focus_id=None,
                es_platform_manager=is_manager_global,
            )

            response = render(
                request,
                "security/htmx/permission_matrix_with_messages.html",
                context,
            )

            response["HX-Push-Url"] = matriz_url
            return response

        return redirect(matriz_url)

    rol_eliminado = rol_instancia.role
    permisos_eliminados = rol_instancia.permissions_list or []

    ForensicAuditor.registrar_evento(
        request=request,
        action_type=SecurityAuditLog.ActionTypes.DELETE,
        module_component="ELIMINACION_MEMBRESIA",
        action_name="PURGA_TOTAL_CREDENCIALES",
        target_scope=(
            f"Destrucción total de privilegios de {target_user.email} "
            f"en {app_module.name}."
        ),
        level=SecurityAuditLog.Levels.CRITICAL,
        target_user=target_user,
        search_target=str(target_user.id),
        payload={
            "deleted_role": rol_eliminado,
            "deleted_permissions": permisos_eliminados,
            "app_id": str(app_module.id),
            "app_slug": app_module.slug,
            "operador_id": str(request.user.id),
            "operador_email": request.user.email,
        },
    )

    rol_instancia.delete()

    messages.warning(
        request,
        f"La membresía de {target_user.email} fue purgada completamente de {app_module.name}.",
    )

    if is_htmx:
        context = build_permission_matrix_context(
            request=request,
            app_module=app_module,
            user_focus_id=None,
            es_platform_manager=is_manager_global,
        )

        response = render(
            request,
            "security/htmx/permission_matrix_with_messages.html",
            context,
        )

        response["HX-Push-Url"] = matriz_url
        return response

    return redirect(matriz_url)


@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="can_modify_matrix")
def matrix_capabilities_view(request):
    """
    Master de capacidades institucionales por app.

    - GET normal: página completa.
    - GET HTMX #workbench: layout con sidebar Security.
    - GET HTMX #page-content: sólo contenido.
    - Selector de app usa app_slug.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    app_slug = (
        request.GET.get("app_slug", "accounts")
        .strip()
        .lower()
    )

    app_activa = get_object_or_404(
        AppModule,
        slug=app_slug,
        is_active=True,
        is_deleted=False,
    )

    context = CapabilitySelectors.obtener_matriz_capacidades_contexto(
        app_activa,
    )

    context.update({
        "apps": (
            AppModule.objects
            .filter(
                is_active=True,
                is_deleted=False,
            )
            .order_by("name")
        ),
        "app_activa": app_activa,
        "modulo_actual": AppIdentifier.SECURITY,
        "show_module_sidebar": True,
        "current_security_view": "security:matrix_capabilities",
    })

    if is_htmx and target_htmx == "workbench":
        return render(
            request,
            "security/workbench/matrix_capabilities_workbench.html",
            context,
        )

    if is_htmx and target_htmx == "page-content":
        return render(
            request,
            "security/content/matrix_capabilities_content.html",
            context,
        )

    return render(
        request,
        "security/pages/matrix_capabilities.html",
        context,
    )


@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="can_modify_matrix")
@require_POST
def add_capability_node_view(request, app_id):
    """
    Vincula una dependencia al mapa relacional de capacidades de una app.

    - Crea AppDependencyCapability si no existe.
    - Si ya existe, avisa sin duplicar.
    - En HTMX repinta la matriz de capacidades con messages_oob.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"

    app_obj = get_object_or_404(
        AppModule,
        id=app_id,
        is_active=True,
        is_deleted=False,
    )

    capabilities_url = (
        reverse("security:matrix_capabilities")
        + f"?app_slug={app_obj.slug}"
    )

    dependencia_id = request.POST.get("dependencia_id")

    if not dependencia_id:
        messages.error(
            request,
            "Selecciona una dependencia válida antes de vincular el nodo.",
        )

        if is_htmx:
            context = CapabilitySelectors.obtener_matriz_capacidades_contexto(
                app_obj,
            )

            context.update({
                "apps": (
                    AppModule.objects
                    .filter(
                        is_active=True,
                        is_deleted=False,
                    )
                    .order_by("name")
                ),
                "app_activa": app_obj,
                "modulo_actual": AppIdentifier.SECURITY,
                "show_module_sidebar": True,
                "current_security_view": "security:matrix_capabilities",
            })

            response = render(
                request,
                "security/htmx/matrix_capabilities_with_messages.html",
                context,
                status=400,
            )

            response["HX-Push-Url"] = capabilities_url
            return response

        return redirect(capabilities_url)

    dep_obj = get_object_or_404(
        Dependencia,
        id=dependencia_id,
        is_deleted=False,
    )

    capacidad, created = AppDependencyCapability.objects.get_or_create(
        app=app_obj,
        dependencia=dep_obj,
        defaults={
            "can_operate": False,
            "can_supervise": False,
            "can_authorize": False,
            "custom_settings": {},
        },
    )

    if created:
        ForensicAuditor.registrar_evento(
            request=request,
            action_type=SecurityAuditLog.ActionTypes.CREATE,
            module_component="MAPA_CAPACIDADES",
            action_name="VINCULACION_NODO_CAPACIDAD",
            target_scope=(
                f"Asignación de derecho de consumo de {app_obj.name} "
                f"a la dependencia {dep_obj.nombre}."
            ),
            level=SecurityAuditLog.Levels.INFO,
            search_target=str(dep_obj.id),
            payload={
                "app_id": str(app_obj.id),
                "app_slug": app_obj.slug,
                "app_name": app_obj.name,
                "dependencia_id": str(dep_obj.id),
                "dependencia_nombre": dep_obj.nombre,
                "capacidad_id": str(capacidad.id),
                "operador_id": str(request.user.id),
                "operador_email": request.user.email,
            },
        )

        messages.success(
            request,
            f"La dependencia {dep_obj.nombre} fue vinculada correctamente a {app_obj.name}.",
        )

    else:
        messages.warning(
            request,
            f"La dependencia {dep_obj.nombre} ya estaba vinculada a {app_obj.name}.",
        )

    if is_htmx:
        context = CapabilitySelectors.obtener_matriz_capacidades_contexto(
            app_obj,
        )

        context.update({
            "apps": (
                AppModule.objects
                .filter(
                    is_active=True,
                    is_deleted=False,
                )
                .order_by("name")
            ),
            "app_activa": app_obj,
            "modulo_actual": AppIdentifier.SECURITY,
            "show_module_sidebar": True,
            "current_security_view": "security:matrix_capabilities",
        })

        response = render(
            request,
            "security/htmx/matrix_capabilities_with_messages.html",
            context,
        )

        response["HX-Push-Url"] = capabilities_url
        return response

    return redirect(capabilities_url)

@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="can_modify_matrix")
@require_POST
def toggle_capability_ajax_view(request, dep_id, app_id):
    """
    Alterna una capacidad de una dependencia dentro de una app.

    Campos válidos:
    - can_operate
    - can_supervise
    - can_authorize
    """

    app_obj = get_object_or_404(
        AppModule,
        id=app_id,
        is_active=True,
        is_deleted=False,
    )

    dep_obj = get_object_or_404(
        Dependencia,
        id=dep_id,
        is_deleted=False,
    )

    field = request.POST.get("field", "").strip()

    campos_validos = {
        "can_operate",
        "can_supervise",
        "can_authorize",
    }

    if field not in campos_validos:
        return HttpResponse(
            "Campo de capacidad inválido.",
            status=400,
        )

    capacidad = get_object_or_404(
        AppDependencyCapability,
        app=app_obj,
        dependencia=dep_obj,
    )

    valor_actual = bool(
        getattr(
            capacidad,
            field,
            False,
        )
    )

    nuevo_valor = not valor_actual

    setattr(
        capacidad,
        field,
        nuevo_valor,
    )

    capacidad.save(
        update_fields=[
            field,
            "updated_at",
        ]
    )

    ForensicAuditor.registrar_evento(
        request=request,
        action_type=SecurityAuditLog.ActionTypes.UPDATE,
        module_component="MAPA_CAPACIDADES",
        action_name="TOGGLE_CAPACIDAD_DEPENDENCIA",
        target_scope=(
            f"Conmutación de capacidad [{field}] para "
            f"{dep_obj.nombre} en {app_obj.name}: {nuevo_valor}."
        ),
        level=SecurityAuditLog.Levels.INFO,
        search_target=str(dep_obj.id),
        payload={
            "app_id": str(app_obj.id),
            "app_slug": app_obj.slug,
            "dependencia_id": str(dep_obj.id),
            "dependencia_nombre": dep_obj.nombre,
            "field": field,
            "previous_value": valor_actual,
            "new_value": nuevo_valor,
            "operador_id": str(request.user.id),
            "operador_email": request.user.email,
        },
    )

    color_on = "bg-blue-600"

    if field == "can_supervise":
        color_on = "bg-indigo-600"

    if field == "can_authorize":
        color_on = "bg-emerald-600"

    return render(
        request,
        "security/partials/capability_toggle.html",
        {
            "cap": capacidad,
            "app_activa": app_obj,
            "field_name": field,
            "field_value": nuevo_valor,
            "color_on": color_on,
            "mobile": request.POST.get("mobile") == "1",
        },
    )


@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="can_view_matrix")
def security_global_matrix_forensic_view(request):
    """
    Auditoría global de matriz de accesos multi-app.

    - Vista completa: shell/workbench.
    - Navegación interna Security: #page-content.
    - Filtros HTMX: #forensic-matrix-results.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    filtros = {
        "q": request.GET.get("q", "").strip(),
        "sede_id": request.GET.get("sede", "").strip() or None,
        "dependencia_id": request.GET.get("dependencia", "").strip() or None,
        "area_id": request.GET.get("area", "").strip() or None,
    }

    funcionarios_liquidados = PermissionSelectors.listar_matriz_forense_global(
        filtros,
    )

    context = {
        "funcionarios": funcionarios_liquidados,
        "aplicaciones_sistema": AppIdentifier.get_choices(),

        "sedes": (
            Sede.objects
            .filter(
                is_active=True,
                is_deleted=False,
            )
            .order_by("nombre")
        ),

        "dependencias": (
            Dependencia.objects
            .filter(
                is_active=True,
                is_deleted=False,
            )
            .order_by("nombre")
        ),

        "areas_operativas": (
            AreaOperativa.objects
            .filter(
                is_active=True,
                is_deleted=False,
            )
            .order_by("nombre")
        ),

        "current_q": filtros["q"],
        "current_sede": str(filtros["sede_id"]) if filtros["sede_id"] else "",
        "current_dep": str(filtros["dependencia_id"]) if filtros["dependencia_id"] else "",
        "current_area": str(filtros["area_id"]) if filtros["area_id"] else "",

        "modulo_actual": AppIdentifier.SECURITY,
        "show_module_sidebar": True,
        "current_security_view": "security:global_matrix_forensic",
    }

    if is_htmx and target_htmx == "workbench":
        return render(
            request,
            "security/workbench/global_matrix_forensic_workbench.html",
            context,
        )

    if is_htmx and target_htmx == "page-content":
        return render(
            request,
            "security/content/global_matrix_forensic_content.html",
            context,
        )

    if is_htmx and target_htmx == "forensic-matrix-results":
        return render(
            request,
            "security/partials/global_matrix_results_partial.html",
            context,
        )

    return render(
        request,
        "security/pages/global_matrix_forensic.html",
        context,
    )



@login_required
@axentra_module_gate(AppIdentifier.SECURITY, required_fine_permission="can_view_analytics")
def descargar_auditoria_excel_view(request):
    """
    Exporta evidencia de auditoría a Excel usando los mismos filtros del dashboard.
    """

    filtros = {
        "app_namespace": request.GET.get("app_namespace", "").strip().lower() or None,
        "action_type": request.GET.get("action_type", "").strip().upper() or None,
        "level_status": request.GET.get("level_status", "").strip().upper() or None,
        "search_target": request.GET.get("search_target", "").strip() or None,
        "operador": request.GET.get("operador", "").strip().lower() or None,
        "fecha_inicio": request.GET.get("fecha_inicio", "").strip() or None,
        "fecha_fin": request.GET.get("fecha_fin", "").strip() or None,
    }

    return PermissionService.exportar_auditoria_excel(
        request=request,
        filtros=filtros,
    )



@login_required
@axentra_module_gate(
    AppIdentifier.CONFIGURATION,
    required_fine_permission="can_view_configuration",
)
def tenant_config_view(request):
    """
    Gobernanza central de identidad institucional / tenant.

    - GET normal: página completa de Configuración.
    - GET HTMX target #workbench: layout con sidebar secundario de Configuración.
    - GET HTMX target #page-content: sólo contenido de identidad institucional.
    - POST normal: guarda y redirige a la propia identidad institucional.
    - POST HTMX: guarda y repinta identidad con messages_oob dentro de Configuración.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    config_instancia = (
        TenantConfig.objects
        .select_related("municipality")
        .first()
    )

    if not config_instancia:
        config_instancia = TenantConfig.objects.create(
            app_name="Axentra OS",
            entidad_nombre="H. Ayuntamiento Constitucional",
            siglas="AXN",
        )

    can_edit_tenant = bool(
        getattr(request, "axentra_is_root", False)
        or "can_configure_tenant" in getattr(
            request,
            "axentra_permissions_list",
            (),
        )
        or "configuration__can_configure_tenant" in getattr(
            request,
            "axentra_permissions_list",
            (),
        )
    )

    if request.method == "POST" and not can_edit_tenant:
        messages.error(
            request,
            "No tiene autorización para modificar la identidad institucional.",
        )
        return redirect("security:tenant_config")

    if request.method == "POST":
        form = TenantConfigForm(
            request.POST,
            request.FILES,
            instance=config_instancia,
        )

        if form.is_valid():
            config_actualizada = form.save()
            config_actualizada.refresh_from_db()

            ForensicAuditor.registrar_evento(
                request=request,
                action_type=SecurityAuditLog.ActionTypes.UPDATE,
                module_component="CONFIGURACION_INSTITUCIONAL",
                action_name="RECONFIGURACION_TENANT_CORE",
                target_scope=(
                    "Modificación de identidad institucional, municipio oficial, "
                    "logotipos, colores o información legal de la entidad."
                ),
                level=SecurityAuditLog.Levels.CRITICAL,
                search_target=config_actualizada.siglas,
                payload={
                    "tenant_id": str(config_actualizada.id),
                    "app_name": config_actualizada.app_name,
                    "entidad_nombre": config_actualizada.entidad_nombre,
                    "siglas": config_actualizada.siglas,
                    "rfc": getattr(config_actualizada, "rfc", ""),
                    "municipality_id": (
                        str(config_actualizada.municipality_id)
                        if config_actualizada.municipality_id
                        else None
                    ),
                    "municipality_code": (
                        config_actualizada.municipality.code
                        if config_actualizada.municipality
                        else ""
                    ),
                    "municipality_name": (
                        config_actualizada.municipality.name
                        if config_actualizada.municipality
                        else ""
                    ),
                    "operador_id": str(request.user.id),
                    "operador_email": request.user.email,
                },
            )

            messages.success(
                request,
                "La identidad institucional se actualizó correctamente.",
            )

            if is_htmx:
                form = TenantConfigForm(
                    instance=config_actualizada,
                )

                context = {
                    "form": form,
                    "config": config_actualizada,
                    "can_edit_tenant": can_edit_tenant,
                    "modulo_actual": AppIdentifier.CONFIGURATION,
                    "show_module_sidebar": True,
                    "current_configuration_view": "security:tenant_config",
                }

                response = render(
                    request,
                    "security/htmx/tenant_config_with_messages.html",
                    context,
                )

                response["HX-Push-Url"] = reverse("security:tenant_config")

                return response

            return redirect("security:tenant_config")

        messages.error(
            request,
            "Revisa los campos del formulario antes de guardar la identidad institucional.",
        )

    else:
        form = TenantConfigForm(
            instance=config_instancia,
        )

    context = {
        "form": form,
        "config": config_instancia,
        "can_edit_tenant": can_edit_tenant,
        "modulo_actual": AppIdentifier.CONFIGURATION,
        "show_module_sidebar": True,
        "current_configuration_view": "security:tenant_config",
    }

    if is_htmx and target_htmx == "workbench":
        return render(
            request,
            "security/workbench/tenant_config_workbench.html",
            context,
        )

    if is_htmx and target_htmx == "page-content":
        return render(
            request,
            "security/content/tenant_config_content.html",
            context,
        )

    return render(
        request,
        "security/pages/tenant_config.html",
        context,
    )


@login_required
@axentra_module_gate(
    AppIdentifier.CONFIGURATION,
    required_fine_permission="can_view_configuration",
)
def privacidad_cookies_view(request):
    """
    Aviso de privacidad y política de cookies institucionales — fuente
    única de verdad legal para toda la instalación (ver
    docs/apps/public-municipal-portal.md: cada satélite instalado por
    separado duplicaba su propio aviso de privacidad antes de esto).

    Sección propia de Configuración, hermana de Identidad Institucional
    en el mismo sidebar (configuration_sidebar.html) — no una cuarta
    pestaña dentro de tenant_config_content.html, que ya tiene tres.
    Mismo Singleton (TenantConfig), mismo permiso (can_configure_tenant:
    ya cubre "datos legales"), mismo patrón de render de tres vías que
    tenant_config_view.

    Mutación (POST) protegida por SudoMiddleware automáticamente — esta
    vista vive bajo el namespace 'security', ya incluido en su lista de
    namespaces protegidos, sin decorador aparte.
    """

    is_htmx = str(request.headers.get("HX-Request", "")).strip().lower() == "true"
    target_htmx = request.headers.get("HX-Target", "")

    config_instancia = TenantConfig.objects.first()

    if not config_instancia:
        config_instancia = TenantConfig.objects.create(
            app_name="Axentra OS",
            entidad_nombre="H. Ayuntamiento Constitucional",
            siglas="AXN",
        )

    can_edit_tenant = bool(
        getattr(request, "axentra_is_root", False)
        or "can_configure_tenant" in getattr(
            request,
            "axentra_permissions_list",
            (),
        )
        or "configuration__can_configure_tenant" in getattr(
            request,
            "axentra_permissions_list",
            (),
        )
    )

    if request.method == "POST" and not can_edit_tenant:
        messages.error(
            request,
            "No tiene autorización para modificar el aviso de privacidad y la política de cookies.",
        )
        return redirect("security:privacidad_cookies")

    if request.method == "POST":
        form = PrivacidadCookiesForm(
            request.POST,
            instance=config_instancia,
        )

        if form.is_valid():
            config_actualizada = form.save()
            config_actualizada.refresh_from_db()

            ForensicAuditor.registrar_evento(
                request=request,
                action_type=SecurityAuditLog.ActionTypes.UPDATE,
                module_component="CONFIGURACION_INSTITUCIONAL",
                action_name="RECONFIGURACION_PRIVACIDAD_COOKIES",
                target_scope=(
                    "Modificación del aviso de privacidad o la política de cookies "
                    "institucionales, visibles en todo el portal público."
                ),
                level=SecurityAuditLog.Levels.CRITICAL,
                search_target=config_actualizada.siglas,
                payload={
                    "tenant_id": str(config_actualizada.id),
                    "operador_id": str(request.user.id),
                    "operador_email": request.user.email,
                },
            )

            messages.success(
                request,
                "El aviso de privacidad y la política de cookies se actualizaron correctamente.",
            )

            if is_htmx:
                form = PrivacidadCookiesForm(
                    instance=config_actualizada,
                )

                context = {
                    "form": form,
                    "config": config_actualizada,
                    "can_edit_tenant": can_edit_tenant,
                    "modulo_actual": AppIdentifier.CONFIGURATION,
                    "show_module_sidebar": True,
                    "current_configuration_view": "security:privacidad_cookies",
                }

                response = render(
                    request,
                    "security/htmx/privacidad_cookies_with_messages.html",
                    context,
                )
                response["HX-Push-Url"] = reverse("security:privacidad_cookies")

                return response

            return redirect("security:privacidad_cookies")

        messages.error(
            request,
            "Revisa los campos del formulario antes de guardar.",
        )

    else:
        form = PrivacidadCookiesForm(
            instance=config_instancia,
        )

    context = {
        "form": form,
        "config": config_instancia,
        "can_edit_tenant": can_edit_tenant,
        "modulo_actual": AppIdentifier.CONFIGURATION,
        "show_module_sidebar": True,
        "current_configuration_view": "security:privacidad_cookies",
    }

    if is_htmx and target_htmx == "workbench":
        return render(
            request,
            "security/workbench/privacidad_cookies_workbench.html",
            context,
        )

    if is_htmx and target_htmx == "page-content":
        return render(
            request,
            "security/content/privacidad_cookies_content.html",
            context,
        )

    return render(
        request,
        "security/pages/privacidad_cookies.html",
        context,
    )

