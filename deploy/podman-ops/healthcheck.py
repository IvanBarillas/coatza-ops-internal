"""Salud del contenedor web: la API responde (401 sin llave = la app y el ruteo funcionan).

Usa el Host `axentra-core` (está en ALLOWED_HOSTS) y una ruta de la API, exenta de la
redirección a HTTPS (SECURE_REDIRECT_EXEMPT=^api/v1/): así no depende del proxy.
"""
import http.client
import sys

conexion = http.client.HTTPConnection("127.0.0.1", 8000, timeout=3)
conexion.request("GET", "/api/v1/tramites/buscar", headers={"Host": "axentra-core"})
sys.exit(0 if conexion.getresponse().status in (200, 401) else 1)
