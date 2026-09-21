"""Enrutamiento por dominio: qué urlconf sirve cada host de la instalación.

Traefik (o el proxy del ayuntamiento) ya decide por ``Host`` a qué contenedor
llega la petición; esto es la mitad de Django: elegir el urlconf según el host
por el que llegó. Se configura con ``AXENTRA_HOST_URLCONFS`` (host -> urlconf);
un host sin entrada usa ``ROOT_URLCONF`` y sin ninguna entrada el middleware no
hace nada, así que el Core sigue arrancando y sirviendo igual que antes.

Debe ir de los primeros en ``MIDDLEWARE``: ``request.urlconf`` tiene que quedar
fijado antes de que Django resuelva la URL.
"""
from django.conf import settings
from django.http.request import split_domain_port


class HostUrlconfMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        mapping = getattr(settings, "AXENTRA_HOST_URLCONFS", None)
        if mapping:
            domain, _port = split_domain_port(request.get_host())
            urlconf = mapping.get(domain)
            if urlconf:
                request.urlconf = urlconf
        return self.get_response(request)


__all__ = ["HostUrlconfMiddleware"]
