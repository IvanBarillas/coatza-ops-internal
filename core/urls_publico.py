# core/urls_publico.py
"""Urlconf de la superficie ciudadana: lo que sirve el dominio público.

Se asigna a un host con ``AXENTRA_HOST_URLCONFS=<host>=core.urls_publico``
(ver apps/shared/middleware/host_urlconf.py). Nada del personal vive aquí:
ni el Hub, ni ``/app/``, ni el admin. Cada satélite instalado aporta sus vistas
públicas bajo el prefijo que declara (``public_prefix`` o ``PUBLIC_PREFIX``).
"""
from django.urls import path

from apps.shared.module_sdk.routing import public_urlpatterns
from core.views import directorio_publico_view

urlpatterns = [
    # La raíz del dominio ciudadano es el directorio de servicios.
    path('', directorio_publico_view, name='directorio_publico_raiz'),
    path('directorio/', directorio_publico_view, name='directorio_publico'),
    *public_urlpatterns(),
]
