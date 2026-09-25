from django.db import transaction
from django.utils import timezone

from . import ocr
from .models import AdjuntoOCR
from .storage import almacen

TAREA_OCR = "satelites.seguimientos_oficios.tasks.procesar_ocr"
TIMEOUT_TAREA = 1800


def procesar_ocr(adjunto_id):
    """Idempotente: si la cola reentrega la tarea mientras otro worker procesa, sale sin hacer nada."""
    with transaction.atomic():
        tomado = AdjuntoOCR.objects.filter(
            adjunto_id=adjunto_id, estado__in=[AdjuntoOCR.Estado.PENDIENTE, AdjuntoOCR.Estado.ERROR]
        ).update(estado=AdjuntoOCR.Estado.PROCESANDO, iniciado_en=timezone.now(), error="")
    if not tomado:
        return "omitido"
    registro = AdjuntoOCR.objects.select_related("adjunto").get(adjunto_id=adjunto_id)
    registro.intentos += 1
    ruta_buscable = registro.adjunto.ruta.removesuffix(".pdf") + "__buscable.pdf"
    try:
        texto = ocr.extraer_texto(almacen().path(registro.adjunto.ruta), almacen().path(ruta_buscable))
    except (ocr.OcrNoDisponible, ocr.OcrFallido) as error:
        registro.estado, registro.error = AdjuntoOCR.Estado.ERROR, str(error)
    else:
        registro.estado, registro.texto = AdjuntoOCR.Estado.LISTO, texto
        registro.ruta_buscable = ruta_buscable if almacen().exists(ruta_buscable) else ""
    registro.terminado_en = timezone.now()
    registro.save()
    return registro.estado
