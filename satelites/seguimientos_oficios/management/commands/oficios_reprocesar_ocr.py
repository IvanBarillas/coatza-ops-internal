from django.core.management.base import BaseCommand
import datetime

from django.utils import timezone

from satelites.seguimientos_oficios import tasks
from satelites.seguimientos_oficios.models import Adjunto, AdjuntoOCR
from satelites.seguimientos_oficios.storage import almacen

FACTOR_PESO_MAXIMO = 2


class Command(BaseCommand):
    help = "Crea el OCR de adjuntos que no lo tienen y reintenta los con error o atascados (sin usar la cola)."

    def add_arguments(self, parser):
        parser.add_argument("--atascados-min", type=int, default=60,
                            help="Minutos tras los que un 'procesando' se considera atascado.")
        parser.add_argument("--buscables", action="store_true",
                            help="Rehace el OCR de los adjuntos ya procesados que no tienen copia con capa de texto "
                                 "(visor) o cuya copia pesa más del doble que el original.")

    def handle(self, *args, **opciones):
        for adjunto in Adjunto.objects.filter(ocr__isnull=True, rol__in=Adjunto.ROLES_CON_OCR):
            AdjuntoOCR.objects.create(adjunto=adjunto)
        if opciones["buscables"]:
            almacen_ = almacen()
            for registro in AdjuntoOCR.objects.filter(
                estado=AdjuntoOCR.Estado.LISTO, adjunto__eliminado=False, adjunto__rol__in=Adjunto.ROLES_CON_OCR,
            ).select_related("adjunto"):
                sin_copia = not registro.ruta_buscable
                pesada = (
                    not sin_copia and almacen_.exists(registro.ruta_buscable) and almacen_.exists(registro.adjunto.ruta)
                    and almacen_.size(registro.ruta_buscable) > FACTOR_PESO_MAXIMO * almacen_.size(registro.adjunto.ruta)
                )
                if sin_copia or pesada:
                    AdjuntoOCR.objects.filter(pk=registro.pk).update(estado=AdjuntoOCR.Estado.PENDIENTE)
        limite = timezone.now() - datetime.timedelta(minutes=opciones["atascados_min"])
        AdjuntoOCR.objects.filter(
            estado=AdjuntoOCR.Estado.PROCESANDO, iniciado_en__lt=limite
        ).update(estado=AdjuntoOCR.Estado.ERROR, error="Atascado; se reintenta.")
        pendientes = AdjuntoOCR.objects.filter(
            estado__in=[AdjuntoOCR.Estado.PENDIENTE, AdjuntoOCR.Estado.ERROR],
            adjunto__rol__in=Adjunto.ROLES_CON_OCR,
        ).values_list("adjunto_id", flat=True)
        for adjunto_id in pendientes:
            resultado = tasks.procesar_ocr(adjunto_id)
            self.stdout.write(f"{adjunto_id}: {resultado}")
