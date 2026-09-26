from io import StringIO

from django.core.management import call_command

from satelites.eventos import carga_ficticia
from satelites.eventos.models import Asignacion, Evento

from .base import BaseEventos


class CargaFicticiaTests(BaseEventos):
    def test_simula_aplica_y_no_duplica(self):
        simulado = carga_ficticia.cargar(carga_ficticia.leer(), aplicar=False)
        self.assertEqual(simulado["eventos"], 5)
        self.assertFalse(Evento.objects.exists())
        real = carga_ficticia.cargar(carga_ficticia.leer(), aplicar=True)
        self.assertEqual((real["tecnicos"], real["eventos"], real["avisos"]), (4, 5, []))
        self.assertEqual(Evento.objects.count(), 5)
        self.assertEqual(Evento.objects.get(nombre__startswith="Feria").estatus, "en_curso")
        self.assertEqual(Evento.objects.get(nombre__startswith="Informe").estatus, "concluido")
        self.assertEqual(Evento.objects.get(nombre__startswith="Feria").asignaciones.count(), 2)
        cantidad = Asignacion.objects.count()
        carga_ficticia.cargar(carga_ficticia.leer(), aplicar=True)
        self.assertEqual((Evento.objects.count(), Asignacion.objects.count()), (5, cantidad))

    def test_comando(self):
        salida = StringIO()
        call_command("eventos_cargar_ficticios", stdout=salida)
        self.assertIn("SIMULACIÓN", salida.getvalue())
        salida = StringIO()
        call_command("eventos_cargar_ficticios", "--aplicar", stdout=salida)
        self.assertIn("eventos nuevos: 5", salida.getvalue())
