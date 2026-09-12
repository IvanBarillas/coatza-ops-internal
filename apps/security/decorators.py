# apps/security/decorators.py
from functools import wraps
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect

from apps.shared.manifest_registry import AxentraOSRegistry
from apps.security.services.permission_loader import get_user_permissions_for_app
from apps.shared.utils.telemetry import AxentraRadar


def _normalizar_module_identifier(module_identifier) -> str:
    """Convierte AppIdentifier / Enum / string a un identificador estable."""
    if hasattr(module_identifier, "value"):
        return str(module_identifier.value).strip().lower()
    return str(module_identifier).strip().lower()


def _es_peticion_htmx(request) -> bool:
    """Detecta peticiones HTMX de forma tolerante."""
    return str(request.headers.get("HX-Request", "")).strip().lower() == "true"


def _usuario_tiene_baja_logica(user) -> bool:
    """Determina si el usuario autenticado está dado de baja lógica."""
    return bool(
        getattr(user, "is_deleted", False)
        or not getattr(user, "is_active", False)
    )


def _resolver_is_root(request) -> bool:
    from apps.security.services.authority import is_platform_admin
    return is_platform_admin(request.user)


def _tiene_permiso_fino(*, permisos: dict, lista_llaves_reales: list, module_identifier: str, required_fine_permission: str) -> bool:
    """Valida permiso fino soportando formatos simples y compuestos."""
    if not required_fine_permission:
        return True
    llave_compuesta = f"{module_identifier}__{required_fine_permission}"
    return bool(
        required_fine_permission in lista_llaves_reales
        or llave_compuesta in lista_llaves_reales
        or permisos.get(required_fine_permission, False)
        or permisos.get(llave_compuesta, False)
    )


def _normalizar_sidebar_item(item):
    """Soporta SIDEBAR_MENU tanto en formato de lista (viejo) como diccionario (nuevo)."""
    if isinstance(item, dict):
        return {
            "icon": item.get("icon", "circle"),
            "name": item.get("name") or item.get("title") or "Sin título",
            "url": item.get("url") or item.get("url_name"),
            "order": item.get("order", 99),
            "permission": item.get("permission"),
        }
    try:
        icon, name_visual, url_name, order, required_perm = item
        return {"icon": icon, "name": name_visual, "url": url_name, "order": order, "permission": required_perm}
    except Exception:
        return None


def _construir_sidebar_menu(*, active_manifest, permisos: dict, lista_llaves_reales: list, module_identifier: str, is_root: bool) -> list:
    """Construye el menú lateral del módulo activo a partir del manifiesto."""
    computed_sidebar = []
    if not active_manifest or not hasattr(active_manifest, "SIDEBAR_MENU"):
        return computed_sidebar

    for raw_item in active_manifest.SIDEBAR_MENU:
        item = _normalizar_sidebar_item(raw_item)
        if not item:
            continue

        required_perm = item.get("permission")
        tiene_llave_permiso = _tiene_permiso_fino(
            permisos=permisos, lista_llaves_reales=lista_llaves_reales, 
            module_identifier=module_identifier, required_fine_permission=required_perm
        ) if required_perm else True

        if is_root or tiene_llave_permiso:
            computed_sidebar.append({
                "icon": item.get("icon", "circle"),
                "name": item.get("name", "Sin título"),
                "url": item.get("url"),
                "order": item.get("order", 99),
                "permission": required_perm,
            })

    computed_sidebar.sort(key=lambda x: x["order"])
    return computed_sidebar


def axentra_module_gate(module_identifier: str, required_fine_permission: str = None):
    """🚧 Guardián funcional autónomo de Axentra OS."""
    module_identifier = _normalizar_module_identifier(module_identifier)

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            is_htmx = _es_peticion_htmx(request)

            # ==========================================================
            # 1. COMPUERTA DE AUTENTICACIÓN
            # ==========================================================
            if not request.user.is_authenticated:
                if is_htmx:
                    return HttpResponseForbidden("Sesión no autenticada. Inicie sesión nuevamente.")
                return redirect("accounts:login")

            # ==========================================================
            # 2. BLOQUEO POR BAJA LÓGICA DEL USUARIO
            # ==========================================================
            if _usuario_tiene_baja_logica(request.user):
                if is_htmx:
                    return HttpResponseForbidden("Acceso denegado: usuario dado de baja lógica.")
                messages.error(request, "⚠️ Su cuenta fue dada de baja lógica. Contacte al administrador.")
                return redirect("accounts:login")

            # El estado institucional del módulo no admite bypass jerárquico.
            # Un root puede administrarlo desde el launcher, pero no operar
            # dentro de un satélite expresamente suspendido.
            from apps.shared.module_sdk.services import get_module_runtime_status
            runtime = get_module_runtime_status(module_identifier)
            if runtime is None or not runtime.available:
                detail = runtime.message if runtime else "El módulo no está instalado."
                if is_htmx:
                    return HttpResponse(detail, status=503)
                messages.warning(request, detail)
                return redirect("index_hub")

            # ==========================================================
            # 3. RESOLUCIÓN DE PERMISOS Y BYPASS
            # ==========================================================
            from apps.security.services.authority import has_governance_bypass
            is_root = has_governance_bypass(request.user, module_identifier)
            permisos = get_user_permissions_for_app(request.user, module_identifier)
            lista_llaves_reales = permisos.get("permissions_list", []) or []
            tiene_acceso_modulo = bool(permisos.get("has_access_module", False) or permisos.get("has_access", False))

            # ==========================================================
            # 4. COMPUERTA DE ACCESO AL MÓDULO
            # ==========================================================
            if not tiene_acceso_modulo and not is_root:
                if is_htmx:
                    return HttpResponseForbidden("Acceso denegado: módulo satélite no autorizado en matriz JSON.")
                messages.error(request, f"⚠️ Acceso denegado al módulo [{module_identifier.upper()}].")
                return redirect("index_hub")

            # ==========================================================
            # 5. COMPUERTA DE PERMISO FINO
            # ==========================================================
            if required_fine_permission and not is_root:
                tiene_permiso = _tiene_permiso_fino(
                    permisos=permisos, lista_llaves_reales=lista_llaves_reales,
                    module_identifier=module_identifier, required_fine_permission=required_fine_permission
                )
                if not tiene_permiso:
                    if is_htmx:
                        return HttpResponseForbidden(f"Acceso denegado: requiere la credencial [{required_fine_permission}].")
                    messages.error(request, f"⚠️ Restricción perimetral: requiere el token [{required_fine_permission}].")
                    return redirect("index_hub")

            # ==========================================================
            # 6. INYECCIÓN DE CONTEXTO Y SIDEBAR
            # ==========================================================
            request.axentra_permissions = permisos
            request.axentra_permissions_list = lista_llaves_reales
            request.axentra_is_root = is_root
            request.axentra_active_module = module_identifier

            active_manifest = AxentraOSRegistry.get_all_manifests().get(module_identifier)
            computed_sidebar = _construir_sidebar_menu(
                active_manifest=active_manifest, permisos=permisos,
                lista_llaves_reales=lista_llaves_reales, module_identifier=module_identifier, is_root=is_root
            )
            request.axentra_sidebar_menu = computed_sidebar

            # ==========================================================
            # 7. TELEMETRÍA Y AUDITORÍA
            # ==========================================================
            try:
                llamado_desde = f"{view_func.__module__} -> {view_func.__name__}()"
            except Exception:
                llamado_desde = "Vista FBV Anónima"

            llaves_vivas = [k for k, v in permisos.items() if v is True and k not in ["has_access", "has_access_module", "llaves", "permissions_list"]]

            AxentraRadar.imprimir_auditoria(
                componente="DECORATOR_GATE", request=request, titulo="Inspector de Aduana de Ruta", icono="🛡️",
                extra_data={
                    "Módulo Target": module_identifier.upper(),
                    "Despachando Vista": llamado_desde,
                    "Token Fino Exigido": required_fine_permission or "NINGUNO (ACCESO LIBRE)",
                    "Enlaces al Sidebar": len(computed_sidebar),
                    "Rango Jerárquico": "👑 MASTER BYPASS ACTIVO" if is_root else "OPERADOR ESTÁNDAR",
                    "Pool Matriz JSON (BD)": llaves_vivas,
                    "Pool Token String (BD)": lista_llaves_reales if lista_llaves_reales else "Sin llaves físicas",
                },
            )

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


# Alias maestro para compatibilidad con views existentes.
axentra_gate_enforcer = axentra_module_gate
