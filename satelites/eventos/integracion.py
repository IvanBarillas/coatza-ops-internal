"""Único punto de contacto con el Core de Axentra.

Ningún otro módulo de la app importa `apps.*`. Para vivir sin el Core basta con reimplementar este archivo.
"""
import uuid

from apps.security.decorators import axentra_module_gate
from apps.shared.module_sdk import ModuleManifest

__all__ = ["ModuleManifest", "nombre_de_usuario", "proteger_vista", "url_de_vale", "usuarios_con_acceso", "usuario_de_prueba"]


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


def url_de_vale(referencia):
    """Dirección para abrir un vale de salida del satélite de préstamos, si está instalado (opcional).

    Con un UUID abre el vale; con un folio o número lleva a la lista de vales. Sin el satélite devuelve None.
    """
    from django.urls import NoReverseMatch, reverse

    try:
        return reverse("seguimientos_oficios:vale_imprimir", args=[uuid.UUID(str(referencia).strip())])
    except (ValueError, NoReverseMatch):
        pass
    try:
        return reverse("seguimientos_oficios:vales")
    except NoReverseMatch:
        return None
