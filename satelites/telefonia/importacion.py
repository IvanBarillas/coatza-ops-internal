"""Importa líneas desde un CSV o desde la exportación KML de Google «Mis mapas» (donde los compañeros de campo ya las tienen).

Del KML se toma el título del punto, las coordenadas y las líneas «Clave: valor» de su descripción (Municipio, Nombre,
Dirección, Teléfono, Paquete, Velocidad). Sin `aplicar` solo simula y reporta.
"""
import csv
import html
import io
import re
import unicodedata
from decimal import Decimal
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from django.db import transaction

from .mapa import coordenadas_de_texto
from .models import Linea, normalizar_identificador

ALIAS = {
    "identificador": ("identificador", "telefono", "linea", "numero", "circuito", "tel"),
    "sitio": ("sitio", "nombre"),
    "titulo": ("titulo", "title"),
    "municipio": ("municipio",),
    "direccion": ("direccion", "domicilio"),
    "paquete": ("paquete", "tipo", "servicio"),
    "velocidad": ("velocidad",),
    "latitud": ("latitud", "lat"),
    "longitud": ("longitud", "lng", "lon", "long"),
    "enlace_maps": ("enlace_maps", "mapa", "google_maps", "url", "enlace"),
}
_INVERSO = {alias: canonico for canonico, alias_ in ALIAS.items() for alias in alias_}


def _clave(texto):
    sin = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sin.lower()).strip("_")


def _canonicas(fila):
    salida = {}
    for clave, valor in fila.items():
        canonico = _INVERSO.get(_clave(clave))
        if canonico and (valor or "").strip():
            salida.setdefault(canonico, valor.strip())
    return salida


def leer_csv(texto):
    muestra = texto[:2048]
    delimitador = ";" if muestra.count(";") > muestra.count(",") else ","
    return [_canonicas(f) for f in csv.DictReader(io.StringIO(texto), delimiter=delimitador)]


def _texto_de_descripcion(crudo):
    limpio = re.sub(r"(?i)<\s*(br|/p|/div|/li|/tr)\s*/?>", "\n", crudo or "")
    return html.unescape(re.sub(r"<[^>]+>", "", limpio))


def leer_kml(texto):
    try:
        raiz = ElementTree.fromstring(texto.encode("utf-8"))
    except ElementTree.ParseError as error:
        raise ValidationError(f"El KML no es válido: {error}") from error
    def local(etiqueta):
        return etiqueta.rpartition("}")[2]
    filas = []
    for punto in (e for e in raiz.iter() if local(e.tag) == "Placemark"):
        campos = {local(h.tag): (h.text or "") for h in punto.iter() if local(h.tag) in ("name", "description", "coordinates")}
        fila = {"titulo": campos.get("name", "").strip()}
        for linea in _texto_de_descripcion(campos.get("description", "")).splitlines():
            coincidencia = re.match(r"^\s*([^:]{2,40}?)\s*:\s*(.+?)\s*$", linea)
            if coincidencia:
                fila[coincidencia.group(1)] = coincidencia.group(2)
        fila = _canonicas(fila)
        coordenadas = campos.get("coordinates", "").strip().split(",")
        if len(coordenadas) >= 2:
            try:
                fila["longitud"], fila["latitud"] = str(float(coordenadas[0])), str(float(coordenadas[1]))
            except ValueError:
                pass
        filas.append(fila)
    return filas


def leer_archivo(nombre, texto):
    return leer_kml(texto) if nombre.lower().endswith((".kml", ".xml")) else leer_csv(texto)


def _tipo(identificador, paquete):
    if re.search(r"[A-Za-z]", identificador):
        return Linea.Tipo.ENLACE
    return Linea.Tipo.INTERNET if "internet" in (paquete or "").lower() else Linea.Tipo.TELEFONO


def _velocidad(fila):
    if fila.get("velocidad"):
        return fila["velocidad"]
    entre_parentesis = re.search(r"\(([^)]+)\)", fila.get("paquete", ""))
    return entre_parentesis.group(1).strip() if entre_parentesis else ""


def _datos_de_fila(fila):
    identificador = " ".join(fila.get("identificador", "").split())
    sitio = fila.get("sitio") or fila.get("titulo", "")
    if not identificador:
        raise ValidationError("Falta el teléfono o circuito.")
    if not sitio:
        raise ValidationError("Falta el nombre del sitio.")
    datos = {
        "sitio": sitio, "municipio": fila.get("municipio", ""), "direccion": fila.get("direccion", ""),
        "tipo": _tipo(identificador, fila.get("paquete", "")), "velocidad": _velocidad(fila),
    }
    coordenadas = None
    if fila.get("latitud") and fila.get("longitud"):
        try:
            coordenadas = (float(fila["latitud"]), float(fila["longitud"]))
        except ValueError:
            raise ValidationError("Latitud o longitud no numéricas.") from None
    elif fila.get("enlace_maps"):
        coordenadas = coordenadas_de_texto(fila["enlace_maps"])
    if coordenadas:
        datos["latitud"], datos["longitud"] = (Decimal(f"{c:.6f}") for c in coordenadas)
    return identificador, {k: v for k, v in datos.items() if v not in ("", None)}


def _distinto(actual, nuevo):
    if isinstance(nuevo, Decimal) or hasattr(actual, "as_tuple"):  # coordenadas: se comparan numéricamente
        return actual is None or round(float(actual), 6) != round(float(nuevo), 6)
    return str(actual) != str(nuevo)


@transaction.atomic
def importar(filas, *, aplicar=False):
    """{'creadas', 'actualizadas', 'sin_cambios', 'errores': [(n, mensaje)]}. Sin `aplicar` no escribe nada."""
    resumen = {"creadas": 0, "actualizadas": 0, "sin_cambios": 0, "errores": []}
    vistas = set()
    for numero, fila in enumerate(filas, start=1):
        try:
            identificador, datos = _datos_de_fila(fila)
        except ValidationError as error:
            resumen["errores"].append((numero, "; ".join(error.messages)))
            continue
        clave = normalizar_identificador(identificador)
        if clave in vistas:
            resumen["errores"].append((numero, f"{identificador} está repetida en el archivo: se toma la primera."))
            continue
        vistas.add(clave)
        existente = Linea.objects.filter(identificador_normalizado=clave).first()
        if existente is None:
            resumen["creadas"] += 1
            if aplicar:
                Linea.objects.create(identificador=identificador, **datos)
            continue
        cambios = {k: v for k, v in datos.items() if _distinto(getattr(existente, k), v)}
        if not cambios:
            resumen["sin_cambios"] += 1
            continue
        resumen["actualizadas"] += 1
        if aplicar:
            for campo, valor in cambios.items():
                setattr(existente, campo, valor)
            existente.save()
    return resumen
