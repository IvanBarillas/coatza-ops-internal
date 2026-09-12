# apps/shared/context_processors.py

import logging

from django.core.exceptions import ObjectDoesNotExist

from apps.security.models import TenantConfig, UserAppRole
from apps.shared.manifest_registry import AxentraOSRegistry
from apps.security.services.permission_loader import get_user_permissions_for_app
from apps.shared.utils.telemetry import AxentraRadar

logger = logging.getLogger(__name__)


def _normalizar_module_identifier(module_identifier) -> str:
    if hasattr(module_identifier, "value"):
        return str(module_identifier.value).strip().lower()
    return str(module_identifier).strip().lower()


def _usuario_es_root(request) -> bool:
    from apps.security.services.authority import is_platform_admin
    return is_platform_admin(request.user)


def _usuario_dado_de_baja(user) -> bool:
    return bool(getattr(user, "is_deleted", False) or not user.is_active)


def _operator_identity(request, modulo_activo="launcher"):
    """Identidad laboral y membresía visible para la barra global."""
    user = request.user
    full_name = (
        getattr(user, "full_name", "")
        or user.get_full_name()
        or user.email
    )
    identity = {
        "name": full_name,
        "email": user.email,
        "role": "Sesión activa",
        "role_code": "",
        "department": "Sin dependencia asignada",
        "area": "Sin área asignada",
        "position": "Sin puesto registrado",
        "module": modulo_activo,
        "is_global_admin": _usuario_es_root(request),
    }

    try:
        profile = user.axentra_profile
    except (AttributeError, ObjectDoesNotExist):
        profile = None

    if profile:
        identity["position"] = profile.puesto or identity["position"]
        area = getattr(profile, "area", None)
        if area:
            identity["area"] = area.nombre
            dependencia = getattr(area, "dependencia", None)
            if dependencia:
                identity["department"] = dependencia.nombre

    if identity["is_global_admin"] and modulo_activo in {"launcher", "security", "configuration"}:
        identity["role"] = "Administrador técnico"
        identity["role_code"] = "root"
        return identity

    if modulo_activo and modulo_activo != "launcher":
        membership = (
            UserAppRole.objects
            .filter(
                user=user,
                app__slug=modulo_activo,
                is_active=True,
                is_deleted=False,
                app__is_active=True,
                app__is_deleted=False,
            )
            .only("role")
            .first()
        )
        if membership:
            identity["role_code"] = membership.role
            identity["role"] = membership.role.replace("_", " ").title()
        else:
            identity["role"] = "Sin rol en este módulo"

    return identity


def _normalizar_sidebar_item(item):
    """
    Soporta SIDEBAR_MENU viejo y nuevo.

    Viejo:
        ["users", "Usuarios", "accounts:funcionario_list", 1, "can_view_list"]

    Nuevo:
        {
            "icon": "users",
            "name": "Usuarios",
            "url": "accounts:funcionario_list",
            "order": 1,
            "permission": "can_view_list",
        }
    """
    if isinstance(item, dict):
        return {
            "icon": item.get("icon", "circle"),
            "name": item.get("name") or item.get("title") or "Sin título",
            "url": item.get("url") or item.get("url_name"),
            "order": item.get("order", 99),
            "permission": item.get("permission"),
        }

    try:
        icon, name, url, order, permission = item
        return {
            "icon": icon,
            "name": name,
            "url": url,
            "order": order,
            "permission": permission,
        }
    except Exception:
        return None


def _tiene_permiso_fino(permisos, lista_llaves, modulo_activo, permiso_req) -> bool:
    if not permiso_req:
        return True

    llave_compuesta = f"{modulo_activo}__{permiso_req}"

    return bool(
        permisos.get(permiso_req, False)
        or permisos.get(llave_compuesta, False)
        or permiso_req in lista_llaves
        or llave_compuesta in lista_llaves
    )


def _filtrar_sidebar_menu(request, modulo_activo, menu_crudo):
    from apps.security.services.authority import has_governance_bypass
    es_root = has_governance_bypass(request.user, modulo_activo)
    menu_filtrado = []

    if es_root:
        for raw_item in menu_crudo:
            item = _normalizar_sidebar_item(raw_item)
            if not item:
                continue

            menu_filtrado.append({
                "icon": item["icon"],
                "name": item["name"],
                "url": item["url"],
                "order": item["order"],
                "permission": item.get("permission"),
            })

        menu_filtrado.sort(key=lambda item: item["order"])
        return menu_filtrado

    permisos = get_user_permissions_for_app(request.user, modulo_activo)
    lista_llaves = permisos.get("permissions_list", []) or []

    for raw_item in menu_crudo:
        item = _normalizar_sidebar_item(raw_item)
        if not item:
            continue

        permiso_req = item.get("permission")

        if _tiene_permiso_fino(
            permisos=permisos,
            lista_llaves=lista_llaves,
            modulo_activo=modulo_activo,
            permiso_req=permiso_req,
        ):
            menu_filtrado.append({
                "icon": item["icon"],
                "name": item["name"],
                "url": item["url"],
                "order": item["order"],
                "permission": permiso_req,
            })

    menu_filtrado.sort(key=lambda item: item["order"])
    return menu_filtrado


def global_tenant_settings(request):
    """
    Inyecta activos de marca e identidad legal a todos los templates.
    """
    try:
        config = TenantConfig.objects.filter(is_deleted=False).first()

        if not config:
            config = TenantConfig.objects.create(
                app_name="Axentra OS",
                entidad_nombre="Axentra Infrastructure",
                siglas="AXN",
                is_active=True,
                is_deleted=False,
            )

        return {"tenant": config}

    except Exception as e:
        logger.error(f"Error en global_tenant_settings: {e}")
        return {"tenant": None}


def user_module_permissions(request):
    """
    Inyecta módulos autorizados para el launcher y sidebar global.
    """
    context = {
        "allowed_modules": [],
        "is_global_admin": False,
    }

    if not request.user.is_authenticated:
        return context

    if _usuario_dado_de_baja(request.user):
        return context

    from django.db.models import Q
    from apps.security.models import AppModule
    from apps.security.services.authority import GOVERNANCE_MODULES
    from apps.shared.module_sdk.registry import module_registry
    scope = Q(roles__user=request.user, roles__is_active=True, roles__is_deleted=False)
    root = _usuario_es_root(request)
    if root:
        scope |= Q(slug__in=GOVERNANCE_MODULES)
    # Una consulta para el menú, sin resolver permisos por cada aplicación.
    allowed = AppModule.objects.filter(
        scope, slug__in=module_registry.codes(), is_active=True, is_deleted=False,
    ).values_list('slug', flat=True).distinct()
    return {'is_global_admin': root, 'allowed_modules': list(allowed)}


def menu_dinamico_processor(request):
    """
    Expone menú contextual calculado por el decorador o reconstruido por fallback.

    Importante:
    - No fuerza sidebar secundario en pantallas directas.
    - Si una vista necesita sidebar contextual, debe enviar show_module_sidebar=True.
    - Este processor sólo expone menu_actual/sidebar_menu para compatibilidad.
    """
    context = {
        "menu_actual": [],
        "modulo_actual": "launcher",
        "sidebar_menu": [],
        "sidebar_secundario": False,
    }

    if not request.user.is_authenticated:
        return context

    if _usuario_dado_de_baja(request.user):
        return context

    modulo_activo = getattr(request, "axentra_active_module", None)

    if not modulo_activo and getattr(request, "resolver_match", None):
        modulo_activo = request.resolver_match.namespace

    modulo_activo = _normalizar_module_identifier(modulo_activo or "launcher")

    context["operator_identity"] = _operator_identity(
        request,
        modulo_activo,
    )

    if not modulo_activo or modulo_activo == "launcher":
        return context

    context["modulo_actual"] = modulo_activo

    if hasattr(request, "axentra_sidebar_menu"):
        menu_final = request.axentra_sidebar_menu or []
        context["menu_actual"] = menu_final
        context["sidebar_menu"] = menu_final
        context["sidebar_secundario"] = False
        return context

    manifiesto_modulo = AxentraOSRegistry.get_manifest_by_slug(modulo_activo)

    if not manifiesto_modulo or not hasattr(manifiesto_modulo, "SIDEBAR_MENU"):
        return context

    menu_filtrado = _filtrar_sidebar_menu(
        request=request,
        modulo_activo=modulo_activo,
        menu_crudo=manifiesto_modulo.SIDEBAR_MENU,
    )

    context["menu_actual"] = menu_filtrado
    context["sidebar_menu"] = menu_filtrado
    context["sidebar_secundario"] = False

    return context

def satellite_navigation(request):
    """
    Construye la navegación global de módulos satélite instalados,
    activos y autorizados para el usuario actual.
    """
    context = {"satellite_navigation": []}

    user = getattr(request, "user", None)

    if (
        not user
        or not user.is_authenticated
        or _usuario_dado_de_baja(user)
    ):
        return context

    from django.urls import NoReverseMatch, reverse

    from apps.shared.module_sdk.contracts import ModuleKind
    from apps.shared.module_sdk.registry import module_registry
    from apps.shared.module_sdk.services import user_can_open_module

    navigation = []

    for manifest in module_registry.discover():
        if manifest.kind != ModuleKind.SATELLITE:
            continue

        if not user_can_open_module(user, manifest.code):
            continue

        try:
            url = reverse(manifest.entry_url)
        except NoReverseMatch:
            continue

        navigation.append(
            {
                "code": manifest.code,
                "name": manifest.name,
                "icon": manifest.icon,
                "url": url,
            }
        )

    context["satellite_navigation"] = navigation
    return context