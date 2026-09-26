"""Único punto de contacto con el Core de Axentra.

Ningún otro módulo de la app importa `apps.*`. Para vivir sin el Core basta con reimplementar este archivo.
"""
from apps.security.decorators import axentra_module_gate
from apps.shared.module_sdk import ModuleManifest
from apps.shared.module_sdk.integrations import integration_registry
from apps.shared.notifications.services import enqueue_email

__all__ = ["ModuleManifest", "tiene_permiso", "lineas", "registrar_proveedor", "enqueue_email", "url_base", "nombre_de_usuario", "proteger_vista", "vales", "usuarios_con_acceso", "usuario_de_prueba"]


def proteger_vista(codigo, permiso):
    return axentra_module_gate(codigo, required_fine_permission=permiso)


def nombre_de_usuario(usuario):
    return (getattr(usuario, "full_name", "") or getattr(usuario, "email", "")) if usuario else ""


def usuarios_con_acceso(app_slug):
    """Usuarios activos con membresía vigente en el módulo (candidatos a técnico)."""
    from django.contrib.auth import get_user_model

    from apps.security.models import UserAppRole

    miembros = UserAppRole.objects.filter(app__slug=app_slug, is_active=True, is_deleted=False).values("user_id")
    return get_user_model().objects.filter(pk__in=miembros, is_active=True, is_deleted=False).order_by("first_name", "email")


def usuario_de_prueba(correo, nombre, apellidos):
    """Usuario sin acceso para los datos ficticios (no tiene contraseña utilizable ni membresías)."""
    from django.contrib.auth import get_user_model

    usuario, creado = get_user_model().objects.get_or_create(
        email=correo, defaults={"first_name": nombre, "last_name": apellidos, "is_email_verified": True},
    )
    if creado:
        usuario.set_unusable_password()
        usuario.save()
    return usuario


def vales():
    """Capacidad opcional `prestamos.vales` (vales de salida). Sin el satélite que la ofrece devuelve una integración nula."""
    return integration_registry.resolve("prestamos.vales")


def url_base():
    """Dirección pública de este satélite (EVENTOS_PUBLIC_BASE_URL) para poner enlaces en los correos; vacía si no se configuró."""
    from django.conf import settings

    return str(getattr(settings, "EVENTOS_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")


def lineas():
    """Capacidad opcional `telefonia.lineas` (líneas y enlaces). Sin el satélite que la ofrece devuelve una integración nula."""
    return integration_registry.resolve("telefonia.lineas")


def registrar_proveedor(nombre, proveedor):
    """Ofrece una capacidad a otros satélites por nombre (ver docs/contratos-satelites.md). Idempotente al reiniciar."""
    integration_registry.register(nombre, proveedor, replace=True)


def tiene_permiso(usuario, app_slug, llave):
    """¿Tiene el usuario ese permiso fino en ese módulo? Los proveedores lo usan porque `request.axentra_permissions_list`
    solo trae los permisos del módulo que atiende la petición, no los del módulo dueño del proveedor."""
    from apps.security.models import UserAppRole

    rol = UserAppRole.objects.filter(
        user=usuario, app__slug=app_slug, app__is_active=True, is_active=True, is_deleted=False,
    ).first()
    return bool(rol and llave in (rol.permissions_list or []))
