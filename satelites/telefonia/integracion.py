"""Único punto de contacto con el Core de Axentra.

Ningún otro módulo de la app importa `apps.*`. Para vivir sin el Core basta con reimplementar este archivo.
"""
from apps.security.decorators import axentra_module_gate
from apps.shared.module_sdk import ModuleManifest

__all__ = ["ModuleManifest", "nombre_de_usuario", "proteger_vista", "usuarios_con_acceso", "valor_entorno"]


def proteger_vista(codigo, permiso):
    return axentra_module_gate(codigo, required_fine_permission=permiso)


def nombre_de_usuario(usuario):
    return (getattr(usuario, "full_name", "") or getattr(usuario, "email", "")) if usuario else ""


def telefono_de_usuario(usuario):
    return getattr(usuario, "phone", "") if usuario else ""


def valor_entorno(nombre, defecto=""):
    """Ajuste propio de la app: setting de Django, variable de entorno o archivo .env del entorno."""
    from django.conf import settings

    valor = getattr(settings, nombre, None)
    if valor:
        return valor
    from core.settings.base import config

    return config(nombre, default=defecto)


def usuarios_con_acceso(app_slug):
    """Usuarios activos con membresía vigente en el módulo (candidatos a responsable de un reporte)."""
    from django.contrib.auth import get_user_model

    from apps.security.models import UserAppRole

    miembros = UserAppRole.objects.filter(app__slug=app_slug, is_active=True, is_deleted=False).values("user_id")
    return get_user_model().objects.filter(pk__in=miembros, is_active=True, is_deleted=False).order_by("first_name", "email")
