import csv
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from . import bandeja
from .models import Adjunto, ClaseDocumento, ConsecutivoFolio, Documento, HistorialDocumento, Nomenclatura
from .services import TAMANO_MAXIMO, _historial, registrar_adjunto

ORIGEN = "importacion"
USUARIO_NOMBRE = "Importación histórica"
CAMPOS_CSV = ("archivo", "sentido", "clase", "fecha", "folio", "contraparte", "asunto", "director")


@dataclass
class Resultado:
    creados: list = field(default_factory=list)
    duplicados: list = field(default_factory=list)
    errores: list = field(default_factory=list)


def _fecha(texto):
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto.strip(), formato).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha no válida: '{texto}' (use AAAA-MM-DD o DD/MM/AAAA).")


def leer_manifiesto(ruta_csv):
    with open(ruta_csv, newline="", encoding="utf-8-sig") as archivo:
        lector = csv.DictReader(archivo)
        if not lector.fieldnames or "archivo" not in lector.fieldnames:
            raise ValueError("El CSV debe tener una columna 'archivo'.")
        return {(fila["archivo"] or "").strip(): fila for fila in lector if (fila.get("archivo") or "").strip()}


def _fecha_del_nombre(nombre, modificado):
    coincidencia = re.match(r"(\d{4}-\d{2}-\d{2})", nombre)
    return _fecha(coincidencia.group(1)) if coincidencia else modificado


def _preparar(direccion, carpeta, nombre, fila, opciones):
    """Devuelve los datos normalizados de un PDF o lanza ValueError con el motivo."""
    fila = fila or {}
    sentido = (fila.get("sentido") or opciones["sentido"] or "").strip()
    if sentido not in Documento.Sentido.values:
        raise ValueError("Falta el sentido (recibido o enviado).")
    clase = (fila.get("clase") or opciones["clase"] or "oficio").strip()
    if clase not in ClaseDocumento.values:
        raise ValueError(f"Clase desconocida: '{clase}'.")
    ruta = carpeta / nombre
    modificado = datetime.fromtimestamp(ruta.stat().st_mtime).date()
    fecha = _fecha(fila["fecha"]) if (fila.get("fecha") or "").strip() else _fecha_del_nombre(nombre, modificado)
    folio = (fila.get("folio") or "").strip()
    nomenclatura = Nomenclatura.objects.filter(direccion=direccion, clase=clase, is_active=True, is_deleted=False).first()
    if not folio and sentido == "enviado" and nomenclatura:
        en_nombre = nomenclatura.interpretar(Path(nombre).stem, buscar=True, tolerante=True)
        if en_nombre:
            folio = nomenclatura.formatear(en_nombre[0], en_nombre[1] or fecha.year)
    if sentido == "enviado" and not folio:
        raise ValueError("Un documento enviado necesita folio (columna 'folio' o en el nombre del archivo).")
    anio = consecutivo = None
    if sentido == "enviado" and nomenclatura:
        interpretado = nomenclatura.interpretar(folio)
        if interpretado:
            consecutivo, anio = interpretado[0], interpretado[1] or fecha.year
    return {
        "sentido": sentido, "clase": clase, "fecha": fecha, "folio": folio, "anio": anio,
        "consecutivo": consecutivo, "nomenclatura": nomenclatura,
        "contraparte": (fila.get("contraparte") or "").strip() or "No especificado",
        "asunto": ((fila.get("asunto") or "").strip() or Path(nombre).stem.replace("_", " "))[:300],
        "director": (fila.get("director") or "").strip(),
    }


def _subir_contador(nomenclatura, anio, consecutivo):
    ConsecutivoFolio.objects.get_or_create(nomenclatura=nomenclatura, anio=anio)
    contador = ConsecutivoFolio.objects.select_for_update().get(nomenclatura=nomenclatura, anio=anio)
    if consecutivo > contador.ultimo:
        contador.ultimo = consecutivo
        contador.save(update_fields=["ultimo"])


@transaction.atomic
def _crear(direccion, nombre, contenido, datos):
    enviado = datos["sentido"] == "enviado"
    documento = Documento.objects.create(
        sentido=datos["sentido"], clase=datos["clase"], direccion=direccion, direccion_nombre=direccion.nombre,
        contraparte=datos["contraparte"], asunto=datos["asunto"], fecha=datos["fecha"], folio=datos["folio"],
        anio=datos["anio"], consecutivo=datos["consecutivo"],
        estado=Documento.Estado.CONCLUIDO if enviado else Documento.Estado.REGISTRADO,
        director_nombre=datos["director"],
    )
    _historial(documento, HistorialDocumento.Accion.CREADO, None, {
        "origen": ORIGEN, "sentido": datos["sentido"], "clase": datos["clase"], "folio": datos["folio"],
        "direccion": direccion.nombre, "director": datos["director"], "contraparte": datos["contraparte"],
        "asunto": datos["asunto"], "fecha": datos["fecha"].isoformat(),
    }, USUARIO_NOMBRE)
    rol = Adjunto.Rol.EVIDENCIA if enviado else Adjunto.Rol.ORIGINAL
    registrar_adjunto(documento, rol=rol, contenido=contenido, nombre=nombre, usuario=None,
                      origen=ORIGEN, encolar=False, usuario_nombre=USUARIO_NOMBRE)
    if enviado and datos["nomenclatura"] and datos["consecutivo"]:
        _subir_contador(datos["nomenclatura"], datos["anio"], datos["consecutivo"])
    return documento


def importar(direccion, carpeta_relativa, *, sentido="", clase="", manifiesto=None, aplicar=False):
    """Importa los PDF de una carpeta de la bandeja. Sin `aplicar` solo valida y reporta."""
    carpeta = bandeja.resolver(carpeta_relativa)
    opciones = {"sentido": sentido, "clase": clase}
    resultado = Resultado()
    pdfs = {a["nombre"] for a in bandeja.listar_pdfs(carpeta)}
    nombres = sorted(pdfs) if manifiesto is None else sorted(manifiesto)
    for faltante in (n for n in nombres if n not in pdfs):
        resultado.errores.append((faltante, "No está en la carpeta."))
    for nombre in (n for n in nombres if n in pdfs):
        try:
            contenido = bandeja.leer(carpeta, nombre, tamano_maximo=TAMANO_MAXIMO)
            if not contenido.startswith(b"%PDF-"):
                raise ValueError("No es un PDF válido.")
            sha256 = hashlib.sha256(contenido).hexdigest()
            if Adjunto.objects.filter(sha256=sha256, documento__direccion=direccion).exists():
                resultado.duplicados.append(nombre)
                continue
            datos = _preparar(direccion, carpeta, nombre, (manifiesto or {}).get(nombre), opciones)
            if aplicar:
                _crear(direccion, nombre, contenido, datos)
            resultado.creados.append((nombre, datos["folio"] or "sin folio", datos["fecha"]))
        except (ValueError, ValidationError, bandeja.BandejaError, IntegrityError) as error:
            mensaje = "; ".join(error.messages) if isinstance(error, ValidationError) else str(error)
            if isinstance(error, IntegrityError):
                mensaje = "Folio repetido para esta dirección."
            resultado.errores.append((nombre, mensaje))
    return resultado
