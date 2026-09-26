"""Único punto de contacto con el Core de Axentra.

Ningún otro módulo de la app importa `apps.*`. Para vivir sin el Core basta con reimplementar este archivo.
"""
from apps.security.decorators import axentra_module_gate
from apps.shared.module_sdk import ModuleManifest
from apps.shared.notifications.services import enqueue_email

__all__ = ["ModuleManifest", "enqueue_email", "usuarios_con_rol", "nombre_de_usuario", "proteger_vista", "sedes_del_core", "usuarios_con_acceso", "usuario_de_prueba"]


def proteger_vista(codigo, permiso):
    return axentra_module_gate(codigo, required_fine_permission=permiso)


def nombre_de_usuario(usuario):
    return (getattr(usuario, "full_name", "") or getattr(usuario, "email", "")) if usuario else ""


def sedes_del_core():
    """[(uuid, nombre)] de las sedes (edificios) activas del Core."""
    from apps.security.models import Sede

    return list(Sede.objects.filter(is_active=True, is_deleted=False).order_by("nombre").values_list("pk", "nombre"))


def usuarios_con_acceso(app_slug):
    """Usuarios activos con membresía vigente en el módulo (candidatos a empleado)."""
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


def usuarios_con_rol(app_slug, roles):
    """Usuarios activos con alguno de esos roles vigentes en el módulo (a quién avisar)."""
    from django.contrib.auth import get_user_model

    from apps.security.models import UserAppRole

    miembros = UserAppRole.objects.filter(app__slug=app_slug, role__in=roles, is_active=True, is_deleted=False).values("user_id")
    return list(get_user_model().objects.filter(pk__in=miembros, is_active=True, is_deleted=False).order_by("first_name", "email"))
