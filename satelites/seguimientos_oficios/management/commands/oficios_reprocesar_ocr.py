from django.core.management.base import BaseCommand
import datetime

from django.utils import timezone

from satelites.seguimientos_oficios import tasks
from satelites.seguimientos_oficios.models import AdjuntoOCR


class Command(BaseCommand):
    help = "Reintenta el OCR de adjuntos con error o atascados en 'procesando' (sin ejecutar en la cola)."

    def add_arguments(self, parser):
        parser.add_argument("--atascados-min", type=int, default=60,
                            help="Minutos tras los que un 'procesando' se considera atascado.")

    def handle(self, *args, **opciones):
        limite = timezone.now() - datetime.timedelta(minutes=opciones["atascados_min"])
        AdjuntoOCR.objects.filter(
            estado=AdjuntoOCR.Estado.PROCESANDO, iniciado_en__lt=limite
        ).update(estado=AdjuntoOCR.Estado.ERROR, error="Atascado; se reintenta.")
        pendientes = AdjuntoOCR.objects.filter(
            estado__in=[AdjuntoOCR.Estado.PENDIENTE, AdjuntoOCR.Estado.ERROR]
        ).values_list("adjunto_id", flat=True)
        for adjunto_id in pendientes:
            resultado = tasks.procesar_ocr(adjunto_id)
            self.stdout.write(f"{adjunto_id}: {resultado}")
