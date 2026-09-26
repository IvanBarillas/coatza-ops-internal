from django.core.management import call_command
from io import StringIO

from apps.security.models import Sede
from satelites.permisos_personal import carga_ficticia
from satelites.permisos_personal.models import Empleado, RangoAntiguedad, Solicitud, UmbralSede

from .base import BasePermisos


class CargaFicticiaTests(BasePermisos):
    def setUp(self):
        super().setUp()
        for nombre in ("Palacio Municipal", "Tesorería Municipal", "Obras Públicas", "Chantli"):
            Sede.objects.get_or_create(nombre=nombre)

    def test_simulacion_no_escribe_y_aplicar_carga_y_es_repetible(self):
        antes = Empleado.objects.count()
        simulado = carga_ficticia.cargar(carga_ficticia.leer(), aplicar=False)
        self.assertEqual(simulado["empleados"], 10)
        self.assertEqual(Empleado.objects.count(), antes)
        real = carga_ficticia.cargar(carga_ficticia.leer(), aplicar=True)
        self.assertEqual((real["empleados"], real["ajustes"], real["avisos"]), (10, 2, []))
        self.assertEqual(Empleado.objects.count(), antes + 10)
        self.assertEqual(RangoAntiguedad.objects.filter(tipo="sindicalizado", desde_anios=15).get().dias_p1, 20)
        self.assertEqual(UmbralSede.objects.get(sede_nombre="Palacio Municipal").minimo, 3)
        cantidad = Solicitud.objects.count()
        self.assertGreater(cantidad, 0)
        carga_ficticia.cargar(carga_ficticia.leer(), aplicar=True)  # segunda vez: no duplica
        self.assertEqual((Empleado.objects.count(), Solicitud.objects.count()), (antes + 10, cantidad))

    def test_los_ficticios_no_tienen_contrasena_ni_acceso(self):
        carga_ficticia.cargar(carga_ficticia.leer(), aplicar=True)
        juan = Empleado.objects.get(usuario__email="juan.perez.f@prueba.axentra.com.mx")
        self.assertFalse(juan.usuario.has_usable_password())
        self.assertFalse(juan.usuario.roles.exists())

    def test_una_sede_inexistente_solo_avisa(self):
        Sede.objects.filter(nombre="Chantli").delete()
        resumen = carga_ficticia.cargar(carga_ficticia.leer(), aplicar=True)
        self.assertTrue(any("Chantli" in a for a in resumen["avisos"]))
        self.assertEqual(Empleado.objects.get(usuario__email="sofia.morales.f@prueba.axentra.com.mx").sede_uuid, None)

    def test_comando(self):
        salida = StringIO()
        call_command("permisos_cargar_ficticios", stdout=salida)
        self.assertIn("SIMULACIÓN", salida.getvalue())
        salida = StringIO()
        call_command("permisos_cargar_ficticios", "--aplicar", stdout=salida)
        self.assertIn("APLICADO", salida.getvalue())
        self.assertIn("empleados: 10", salida.getvalue())
