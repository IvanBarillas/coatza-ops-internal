"""Único punto de contacto con el Core de Axentra.

Ningún otro módulo de la app importa `apps.*`. Para vivir sin el Core basta con reimplementar este archivo.
"""
from apps.security.decorators import axentra_module_gate
from apps.shared.module_sdk import ModuleManifest
from apps.shared.module_sdk.integrations import integration_registry

__all__ = ["ModuleManifest", "tiene_permiso", "registrar_proveedor", "vinculos_de", "nombre_de_usuario", "proteger_vista", "usuarios_con_acceso", "valor_entorno"]


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


# Proveedores de `vinculos_de` que puede haber en la instalación (ver docs/contratos-satelites.md); solo son nombres, no código de otros satélites.
PROVEEDORES_DE_VINCULOS = ("vinculos.eventos",)


def registrar_proveedor(nombre, proveedor):
    """Ofrece una capacidad a otros satélites por nombre (ver docs/contratos-satelites.md). Idempotente al reiniciar."""
    integration_registry.register(nombre, proveedor, replace=True)


def vinculos_de(request, tipo, ref_id):
    """Fichas de lo que otros satélites tienen relacionado con este objeto (tipo + UUID). Vacío si ninguno lo ofrece."""
    fichas = []
    for nombre in PROVEEDORES_DE_VINCULOS:
        fichas.extend(integration_registry.resolve(nombre).vinculos_de(request, tipo, ref_id) or [])
    return fichas


def tiene_permiso(usuario, app_slug, llave):
    """¿Tiene el usuario ese permiso fino en ese módulo? Los proveedores lo usan porque `request.axentra_permissions_list`
    solo trae los permisos del módulo que atiende la petición, no los del módulo dueño del proveedor."""
    from apps.security.models import UserAppRole

    rol = UserAppRole.objects.filter(
        user=usuario, app__slug=app_slug, app__is_active=True, is_active=True, is_deleted=False,
    ).first()
    return bool(rol and llave in (rol.permissions_list or []))
