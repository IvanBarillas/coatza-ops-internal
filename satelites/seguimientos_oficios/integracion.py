"""Único punto de contacto con el Core de Axentra.

Ningún otro módulo de la app importa `apps.*`. Para vivir sin el Core basta con
reimplementar este archivo.
"""
from apps.security.decorators import axentra_module_gate
from apps.shared.module_sdk import ModuleManifest
from apps.shared.module_sdk.data_access import authorized_departments
from apps.shared.notifications.services import enqueue_email

__all__ = [
    "valor_entorno",
    "ModuleManifest",
    "dependencias_autorizadas",
    "director_de_dependencia",
    "encolar_tarea",
    "enqueue_email",
    "nombre_de_usuario",
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


def director_de_dependencia(dependencia_uuid):
    """Nombre del titular actual de la dependencia del Core, o cadena vacía."""
    from apps.security.models import Dependencia

    if not dependencia_uuid:
        return ""
    dependencia = (
        Dependencia.objects.select_related("encargado_departamento")
        .filter(pk=dependencia_uuid).first()
    )
    titular = dependencia.encargado_departamento if dependencia else None
    return (titular.full_name or titular.email) if titular else ""


def nombre_de_usuario(usuario):
    return (getattr(usuario, "full_name", "") or getattr(usuario, "email", "")) if usuario else ""


def encolar_tarea(ruta_funcion, *args, timeout=None):
    """Encola una tarea en la cola del Core (Django-Q2)."""
    from django_q.tasks import async_task

    opciones = {"timeout": timeout} if timeout else {}
    return async_task(ruta_funcion, *args, **opciones)


def valor_entorno(nombre, defecto=""):
    """Ajuste propio de la app: setting de Django, variable de entorno o archivo .env del entorno."""
    from django.conf import settings

    valor = getattr(settings, nombre, None)
    if valor:
        return valor
    from core.settings.base import config

    return config(nombre, default=defecto)
