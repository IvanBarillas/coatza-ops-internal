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


def public_urlpatterns():
    """Vistas públicas de los satélites instalados, cada una bajo su prefijo.

    Es lo que sirve ``core.urls_publico`` en el dominio del ciudadano; nunca se
    mezcla con el urlconf de personal (los ``app_name`` públicos y de panel de un
    mismo satélite pueden coincidir).
    """
    return [path(surface.prefix, include(surface.urlconf)) for surface in module_registry.public_surfaces()]


__all__ = ["public_urlpatterns", "satellite_urlpatterns"]
