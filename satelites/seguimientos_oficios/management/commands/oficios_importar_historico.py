from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from satelites.seguimientos_oficios import importacion
from satelites.seguimientos_oficios.bandeja import BandejaError
from satelites.seguimientos_oficios.models import Direccion


class Command(BaseCommand):
    help = (
        "Importa PDF ya digitalizados de una carpeta de la bandeja como documentos. "
        "Sin --aplicar solo valida y muestra qué haría."
    )

    def add_arguments(self, parser):
        parser.add_argument("--direccion", required=True, help="Carpeta (slug) o nombre de la dirección.")
        parser.add_argument("--carpeta", required=True, help="Carpeta relativa a OFICIOS_BANDEJA_RAIZ.")
        parser.add_argument("--sentido", choices=["recibido", "enviado"], default="")
        parser.add_argument("--clase", default="", help="Clase de documento (por defecto oficio).")
        parser.add_argument("--csv", default="", help="Manifiesto CSV: archivo,sentido,clase,fecha,folio,contraparte,asunto,director.")
        parser.add_argument("--aplicar", action="store_true", help="Escribe en la base; sin esto es una simulación.")

    def handle(self, *args, **opciones):
        direccion = Direccion.objects.filter(Q(slug=opciones["direccion"]) | Q(nombre=opciones["direccion"])).first()
        if direccion is None:
            raise CommandError(f"No existe la dirección '{opciones['direccion']}'.")
        manifiesto = None
        if opciones["csv"]:
            try:
                manifiesto = importacion.leer_manifiesto(opciones["csv"])
            except (OSError, ValueError) as error:
                raise CommandError(f"CSV no válido: {error}") from error
        try:
            resultado = importacion.importar(
                direccion, opciones["carpeta"], sentido=opciones["sentido"], clase=opciones["clase"],
                manifiesto=manifiesto, aplicar=opciones["aplicar"],
            )
        except BandejaError as error:
            raise CommandError(str(error)) from error
        modo = "Importados" if opciones["aplicar"] else "Se importarían (simulación)"
        self.stdout.write(f"{modo}: {len(resultado.creados)}")
        for nombre, folio, fecha in resultado.creados:
            self.stdout.write(f"  + {nombre} · {folio} · {fecha}")
        self.stdout.write(f"Ya existentes (omitidos): {len(resultado.duplicados)}")
        for nombre in resultado.duplicados:
            self.stdout.write(f"  = {nombre}")
        self.stdout.write(f"Con error: {len(resultado.errores)}")
        for nombre, motivo in resultado.errores:
            self.stdout.write(self.style.ERROR(f"  ! {nombre}: {motivo}"))
        if opciones["aplicar"] and resultado.creados:
            self.stdout.write("Para extraer el texto: python manage.py oficios_reprocesar_ocr")
