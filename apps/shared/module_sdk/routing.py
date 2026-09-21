from django.urls import include, path

from .registry import module_registry


def satellite_urlpatterns():
    """Monta sólo los urlconf publicados por módulos realmente instalados.

    ``urlconf``/``url_prefix`` es el panel de personal (Hub); ``api_urlconf``/
    ``api_prefix`` es la API servicio-a-servicio. Varios satélites pueden
    compartir ``api_prefix`` (``api/v1/``) mientras sus rutas y el
    ``urls_namespace`` de cada API no choquen.
    """
    patterns = []
    for manifest in module_registry.discover():
        if manifest.urlconf and manifest.url_prefix:
            patterns.append(path(manifest.url_prefix, include(manifest.urlconf)))
        if manifest.api_urlconf and manifest.api_prefix:
            patterns.append(path(manifest.api_prefix, include(manifest.api_urlconf)))
    return patterns


__all__ = ["satellite_urlpatterns"]
