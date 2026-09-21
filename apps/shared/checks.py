"""Comprobaciones de arranque de las superficies de una instalación real."""
from importlib import import_module

from django.conf import settings
from django.core.checks import Error, Warning, register
from django.http.request import validate_host


@register()
def check_installation_surfaces(app_configs, **kwargs):
    issues = []

    for host, urlconf in (getattr(settings, "AXENTRA_HOST_URLCONFS", None) or {}).items():
        try:
            module = import_module(urlconf)
        except ImportError as exc:
            issues.append(Error(
                f"AXENTRA_HOST_URLCONFS: el urlconf {urlconf!r} de {host!r} no se puede importar ({exc}).",
                hint="Instale el paquete que lo publica o quite la entrada de AXENTRA_HOST_URLCONFS.",
                id="axentra.E001",
            ))
            continue
        if not hasattr(module, "urlpatterns"):
            issues.append(Error(
                f"AXENTRA_HOST_URLCONFS: {urlconf!r} no define urlpatterns.",
                id="axentra.E002",
            ))
        if not validate_host(host, settings.ALLOWED_HOSTS):
            issues.append(Warning(
                f"El host {host!r} de AXENTRA_HOST_URLCONFS no está en ALLOWED_HOSTS: Django lo rechazará con 400.",
                id="axentra.W001",
            ))

    if not getattr(settings, "INTERNAL_API_KEY", ""):
        from apps.shared.module_sdk.registry import module_registry

        with_api = [m.code for m in module_registry.discover() if m.api_urlconf]
        if with_api:
            issues.append(Warning(
                f"Los módulos {', '.join(with_api)} publican API pero INTERNAL_API_KEY está vacía: "
                "ninguna petición se autenticará.",
                id="axentra.W002",
            ))
    return issues
