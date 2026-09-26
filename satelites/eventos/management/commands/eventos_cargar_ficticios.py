from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from satelites.eventos.carga_ficticia import ARCHIVO, cargar, leer


class Command(BaseCommand):
    help = "Carga datos FICTICIOS para probar Eventos (técnicos de prueba y eventos). Sin --aplicar solo simula. Es repetible: no duplica."

    def add_arguments(self, parser):
        parser.add_argument("--archivo", default=str(ARCHIVO), help="JSON con los datos (por defecto, el que viene con la app)")
        parser.add_argument("--aplicar", action="store_true", help="Escribe los datos (por defecto solo simula)")

    def handle(self, *args, **opciones):
        try:
            resumen = cargar(leer(opciones["archivo"]), aplicar=opciones["aplicar"])
        except (OSError, ValueError, KeyError, ValidationError) as error:
            raise CommandError(f"No se pudo cargar: {error}") from error
        self.stdout.write("APLICADO" if opciones["aplicar"] else "SIMULACIÓN (use --aplicar para escribir)")
        self.stdout.write(f"  técnicos: {resumen['tecnicos']} · eventos nuevos: {resumen['eventos']} · asignaciones: {resumen['asignaciones']}")
        for aviso in resumen["avisos"]:
            self.stdout.write(f"  aviso: {aviso}")
