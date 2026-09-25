from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from satelites.telefonia.importacion import importar, leer_archivo


class Command(BaseCommand):
    help = (
        "Importa líneas desde un CSV o desde el KML exportado de Google «Mis mapas». Sin --aplicar solo simula. "
        "Repetirlo es seguro: las líneas existentes (por número o circuito) se actualizan, no se duplican."
    )

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Ruta del .csv o .kml")
        parser.add_argument("--aplicar", action="store_true", help="Escribe los cambios (por defecto solo simula)")

    def handle(self, *args, **opciones):
        ruta = Path(opciones["archivo"])
        if not ruta.is_file():
            raise CommandError(f"No existe el archivo {ruta}.")
        try:
            filas = leer_archivo(ruta.name, ruta.read_text(encoding="utf-8-sig"))
            resumen = importar(filas, aplicar=opciones["aplicar"])
        except (ValidationError, UnicodeDecodeError) as error:
            raise CommandError(str(error)) from error
        modo = "APLICADO" if opciones["aplicar"] else "SIMULACIÓN (use --aplicar para escribir)"
        self.stdout.write(f"{modo}: {len(filas)} fila(s) leída(s)")
        self.stdout.write(f"  creadas: {resumen['creadas']} · actualizadas: {resumen['actualizadas']} · sin cambios: {resumen['sin_cambios']}")
        for numero, mensaje in resumen["errores"]:
            self.stdout.write(self.style.WARNING(f"  fila {numero}: {mensaje}"))
