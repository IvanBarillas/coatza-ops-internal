
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.security.models import AppModule, UserAppRole
from apps.security.models.audit import SecurityAuditLog

from .contracts import ModuleHealth, ModuleRuntimeStatus
from .catalog import available_module_catalog
from .registry import module_registry


def sync_installed_modules():
    """Aprovisiona metadatos sin reactivar módulos suspendidos."""
    synchronized = []
    for manifest in module_registry.discover():
        defaults = {
            "name": manifest.name,
            "description": manifest.description,
            "version": manifest.version,
            "icon": manifest.icon,
            "entry_url_name": manifest.entry_url,
            "module_kind": manifest.kind.value,
            "dependencies": list(manifest.dependencies),
            "optional_integrations": list(manifest.optional_integrations),
            "is_active": manifest.default_enabled,
            "is_deleted": False,
        }
        module, created = AppModule.objects.get_or_create(
            slug=manifest.code,
            defaults=defaults,
        )
        if not created:
            changed = []
            for field, value in defaults.items():
                if field in {"is_active", "is_deleted"}:
                    continue
                if getattr(module, field) != value:
                    setattr(module, field, value)
                    changed.append(field)
            if module.is_deleted:
                module.is_deleted = False
                module.deleted_at = None
                changed.extend(["is_deleted", "deleted_at"])
            if not manifest.can_disable and not module.is_active:
                module.is_active = True
                changed.append("is_active")
            if changed:
                module.save(update_fields=[*changed, "updated_at"])
        synchronized.append(module)
    return tuple(synchronized)


def get_module_runtime_status(code, *, persist=False, _cache=None):
    """Calcula el estado operativo de un módulo.

    ``_cache`` es un diccionario opcional, con vida útil acotada a una sola
    llamada de alto nivel (por ejemplo ``launcher_cards``), que evita repetir
    las mismas consultas cuando el mismo código se resuelve más de una vez
    en la misma operación. No se comparte entre requests ni persiste en el
    proceso, para no servir estados de módulo obsoletos tras un toggle.
    """
    if _cache is not None and not persist and code in _cache:
        return _cache[code]

    manifest = module_registry.get(code)
    if manifest is None:
        return None
    module = AppModule.objects.filter(slug=manifest.code, is_deleted=False).first()
    enabled = module.is_active if module else manifest.default_enabled
    missing = []
    for dependency in manifest.dependencies:
        dependency_manifest = module_registry.get(dependency)
        dependency_row = AppModule.objects.filter(
            slug=dependency,
            is_deleted=False,
            is_active=True,
        ).exists()
        if dependency_manifest is None or not dependency_row:
            missing.append(dependency)

    if not enabled:
        health = ModuleHealth.DISABLED
        message = "El módulo está deshabilitado para esta institución."
    elif missing:
        health = ModuleHealth.UNAVAILABLE
        message = "Faltan dependencias activas: " + ", ".join(missing)
    else:
        try:
            reverse(manifest.entry_url)
        except NoReverseMatch:
            health = ModuleHealth.WARNING
            message = "La ruta de entrada todavía no está conectada."
        else:
            health = ModuleHealth.HEALTHY
            message = "Módulo listo para operar."

    status = ModuleRuntimeStatus(
        manifest=manifest,
        installed=True,
        enabled=enabled,
        health=health,
        message=message,
        missing_dependencies=tuple(missing),
    )
    if persist and module:
        module.health_status = health.value
        module.health_message = message[:255]
        module.last_health_check_at = timezone.now()
        module.save(update_fields=[
            "health_status", "health_message", "last_health_check_at", "updated_at"
        ])

    if _cache is not None and not persist:
        _cache[code] = status

    return status


def _is_root(user):
    from apps.security.services.authority import is_platform_admin
    return is_platform_admin(user)


def user_can_open_module(user, code, *, _cache=None):
    status = get_module_runtime_status(code, _cache=_cache)
    if not status or not status.available or not user or not user.is_authenticated:
        return False
    if not user.is_active or user.is_deleted:
        return False
    from apps.security.services.permission_loader import get_user_permissions_for_app
    permissions = get_user_permissions_for_app(user, code)
    return bool(permissions.get('has_access_module'))


def launcher_cards(user):
    """Construye las tarjetas del launcher a partir de módulos ya instalados.

    No sincroniza metadatos: eso es responsabilidad exclusiva de
    ``post_migrate`` (ver ``apps.security.apps``) y de los comandos de
    management (``bootstrap_axentra_owner``, ``check_axentra_modules``).
    """
    cards = []
    root = _is_root(user)
    # Cache de una sola pasada: evita recalcular get_module_runtime_status
    # para el mismo módulo cuando user_can_open_module lo vuelve a resolver.
    status_cache = {}
    for manifest in module_registry.discover():
        status = get_module_runtime_status(manifest.code, persist=False, _cache=status_cache)
        try:
            url = reverse(manifest.entry_url)
        except NoReverseMatch:
            url = ""
        cards.append({
            "code": manifest.code,
            "name": manifest.name,
            "description": manifest.description,
            "version": manifest.version,
            "icon": manifest.icon,
            "kind": manifest.kind.value,
            "enabled": status.enabled,
            "health": status.health.value,
            "health_label": status.health.value.replace("_", " ").title(),
            "message": status.message,
            "url": url,
            "can_open": user_can_open_module(user, manifest.code, _cache=status_cache),
            "can_toggle": root and manifest.can_disable,
            "dependencies": manifest.dependencies,
            "optional_integrations": manifest.optional_integrations,
        })
    return tuple(cards)


def public_directory_cards():
    """Tarjetas del directorio público (sin sesión) para el ciudadano.

    Solo aparecen los módulos que declaran ``entry_url_publico`` y están
    habilitados. No usa ``get_module_runtime_status``: su chequeo de salud
    resuelve ``entry_url`` (ruta de personal) y daría falsos negativos aquí.
    """
    cards = []
    for manifest in module_registry.discover():
        if not manifest.entry_url_publico:
            continue
        module = AppModule.objects.filter(slug=manifest.code, is_deleted=False).first()
        enabled = module.is_active if module else manifest.default_enabled
        if not enabled:
            continue
        cards.append({
            "code": manifest.code,
            "name": manifest.name,
            "description": manifest.description,
            "icon": manifest.icon,
            "url": manifest.entry_url_publico,
        })
    return tuple(cards)


def module_center_cards(user):
    """Combina productos conocidos con los módulos realmente instalados."""
    installed_cards = {
        card["code"]: {**card, "installed": True, "state": "INSTALLED"}
        for card in launcher_cards(user)
    }
    catalog = {entry.code: entry for entry in available_module_catalog()}
    root = _is_root(user)

    cards = []
    installed_manifests = module_registry.discover()
    ordered_codes = [manifest.code for manifest in installed_manifests]
    ordered_codes.extend(
        code for code in catalog if code not in installed_cards
    )

    for code in ordered_codes:
        product = catalog.get(code)
        if code in installed_cards:
            card = installed_cards[code]
            card.update({
                "distribution": product.distribution if product else "",
                "install_steps": product.install_steps if product else (),
                "catalogued": product is not None,
                "can_view_installation": root and product is not None,
            })
        else:
            card = {
                "code": product.code,
                "name": product.name,
                "description": product.description,
                "version": "",
                "icon": product.icon,
                "kind": product.kind.value,
                "enabled": False,
                "installed": False,
                "state": "NOT_INSTALLED",
                "health": "NOT_INSTALLED",
                "health_label": "No instalado",
                "message": "El producto está disponible, pero su código no está instalado.",
                "url": "",
                "can_open": False,
                "can_toggle": False,
                "dependencies": product.dependencies,
                "optional_integrations": (),
                "distribution": product.distribution,
                "install_steps": product.install_steps,
                "catalogued": True,
                "can_view_installation": root,
            }
        cards.append(card)
    return tuple(cards)


def module_center_summary(cards):
    cards = tuple(cards)
    return {
        "known": len(cards),
        "installed": sum(1 for card in cards if card["installed"]),
        "active": sum(
            1 for card in cards
            if card["installed"] and card["enabled"]
        ),
        "available": sum(1 for card in cards if not card["installed"]),
        "attention": sum(
            1 for card in cards
            if card["installed"]
            and card["enabled"]
            and card["health"] != ModuleHealth.HEALTHY.value
        ),
    }


@transaction.atomic
def set_module_enabled(*, code, enabled, actor, request=None):
    if not _is_root(actor):
        raise PermissionDenied("Sólo un administrador global puede cambiar módulos.")
    manifest = module_registry.get(code)
    if not manifest:
        raise ValidationError("El módulo no está instalado.")
    if not enabled and not manifest.can_disable:
        raise ValidationError("Este componente pertenece al núcleo y no puede desactivarse.")
    module = AppModule.objects.select_for_update().get(slug=manifest.code, is_deleted=False)
    if enabled:
        missing = [
            dep for dep in manifest.dependencies
            if not AppModule.objects.filter(slug=dep, is_active=True, is_deleted=False).exists()
        ]
        if missing:
            raise ValidationError(
                "Active primero las dependencias: " + ", ".join(missing)
            )
    else:
        active_dependents = []
        for candidate in module_registry.discover():
            if manifest.code in candidate.dependencies and AppModule.objects.filter(
                slug=candidate.code, is_active=True, is_deleted=False
            ).exists():
                active_dependents.append(candidate.name)
        if active_dependents:
            raise ValidationError(
                "No puede desactivarse mientras dependan de él: "
                + ", ".join(active_dependents)
            )
    previous_state = module.is_active
    module.is_active = bool(enabled)
    module.health_status = (
        ModuleHealth.HEALTHY.value if enabled else ModuleHealth.DISABLED.value
    )
    module.health_message = (
        "Módulo habilitado por un administrador global."
        if enabled else "Módulo deshabilitado por un administrador global."
    )
    module.last_health_check_at = timezone.now()
    module.save(update_fields=[
        "is_active", "health_status", "health_message",
        "last_health_check_at", "updated_at",
    ])
    SecurityAuditLog.objects.create(
        app_namespace="core",
        action_type=SecurityAuditLog.ActionTypes.UPDATE,
        module_component="MODULE_SDK",
        level_status=(
            SecurityAuditLog.Levels.SUCCESS
            if enabled else SecurityAuditLog.Levels.CRITICAL
        ),
        action_name=("ACTIVACIÓN DE MÓDULO" if enabled else "DESACTIVACIÓN DE MÓDULO"),
        search_target=manifest.code,
        target_scope=f"Módulo institucional: {manifest.name}",
        operator_user=actor,
        ip_address=(
            request.META.get("REMOTE_ADDR", "127.0.0.1")
            if request else "127.0.0.1"
        ),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") if request else ""),
        payload_json={
            "module": manifest.code,
            "before": {"is_active": previous_state},
            "after": {"is_active": bool(enabled)},
            "previous_enabled": previous_state,
            "enabled": bool(enabled),
            "version": manifest.version,
        },
    )
    return module


__all__ = [
    "get_module_runtime_status",
    "launcher_cards",
    "module_center_cards",
    "module_center_summary",
    "public_directory_cards",
    "set_module_enabled",
    "sync_installed_modules",
    "user_can_open_module",
]
