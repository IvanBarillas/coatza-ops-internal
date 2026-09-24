"""Único punto de contacto con el Core de Axentra.

Ningún otro módulo de la app importa `apps.*`. Para vivir sin el Core basta con
reimplementar este archivo.
"""
from apps.security.decorators import axentra_module_gate
from apps.shared.module_sdk import ModuleManifest
from apps.shared.module_sdk.data_access import authorized_departments
from apps.shared.notifications.services import enqueue_email

__all__ = [
    "ModuleManifest",
    "dependencias_autorizadas",
    "enqueue_email",
    "proteger_vista",
]


def proteger_vista(codigo, permiso):
    return axentra_module_gate(codigo, required_fine_permission=permiso)


def dependencias_autorizadas(usuario, *, app_slug, permiso):
    """UUIDs de las dependencias del Core cuyos datos puede ver el usuario."""
    return set(
        authorized_departments(usuario, app_slug=app_slug, permission=permiso)
        .values_list("pk", flat=True)
    )
