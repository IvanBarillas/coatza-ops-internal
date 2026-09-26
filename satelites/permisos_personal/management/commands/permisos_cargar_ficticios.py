from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from satelites.permisos_personal.carga_ficticia import ARCHIVO, cargar, leer


class Command(BaseCommand):
    help = (
        "Carga datos FICTICIOS para probar Permisos del personal (configuración, tabla por antigüedad, mínimos por sede, "
        "empleados y unas solicitudes). Sin --aplicar solo simula. Es repetible: no duplica."
    )

    def add_arguments(self, parser):
        parser.add_argument("--archivo", default=str(ARCHIVO), help="JSON con los datos (por defecto, el que viene con la app)")
        parser.add_argument("--aplicar", action="store_true", help="Escribe los datos (por defecto solo simula)")

    def handle(self, *args, **opciones):
        try:
            resumen = cargar(leer(opciones["archivo"]), aplicar=opciones["aplicar"])
        except (OSError, ValueError, KeyError, ValidationError) as error:
            raise CommandError(f"No se pudo cargar: {error}") from error
        modo = "APLICADO" if opciones["aplicar"] else "SIMULACIÓN (use --aplicar para escribir)"
        self.stdout.write(modo)
        self.stdout.write(
            f"  empleados: {resumen['empleados']} · filas de antigüedad: {resumen['rangos']} · mínimos por sede: {resumen['umbrales']} · "
            f"ajustes: {resumen['ajustes']} · solicitudes de ejemplo: {resumen['solicitudes']}"
        )
        for aviso in resumen["avisos"]:
            self.stdout.write(self.style.WARNING(f"  {aviso}"))
