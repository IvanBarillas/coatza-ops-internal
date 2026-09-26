"""Coordenadas a partir de lo que la gente pega de Google Maps (enlace largo, «lat, lng» o parámetros de la URL)."""
import re

_NUM = r"(-?\d{1,3}\.\d+)"
_PATRONES = (
    re.compile(r"!3d" + _NUM + r"!4d" + _NUM),
    re.compile(r"@" + _NUM + r"," + _NUM),
    re.compile(r"[?&](?:q|ll|query|center)=" + _NUM + r"(?:,|%2C)\s*" + _NUM),
    re.compile(r"^\s*" + _NUM + r"\s*[,;\s]\s*" + _NUM + r"\s*$"),
)


def coordenadas_de_texto(texto):
    """(latitud, longitud) o None. Solo acepta valores dentro del rango geográfico válido."""
    for patron in _PATRONES:
        coincidencia = patron.search(texto or "")
        if coincidencia:
            latitud, longitud = float(coincidencia.group(1)), float(coincidencia.group(2))
            if -90 <= latitud <= 90 and -180 <= longitud <= 180:
                return latitud, longitud
    return None
