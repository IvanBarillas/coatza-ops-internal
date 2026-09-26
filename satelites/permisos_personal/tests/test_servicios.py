import datetime
import uuid

from django.core.exceptions import ValidationError

from satelites.permisos_personal import services as svc
from satelites.permisos_personal.models import Configuracion, Solicitud, UmbralSede

from .base import LUNES, BasePermisos, d

VAC, ECO = svc.VACACIONES, svc.ECONOMICO


class SaldosTests(BasePermisos):
    def test_vacaciones_salen_de_la_tabla_por_antiguedad_y_cada_periodo_puede_diferir(self):
        # Ana ingresó en 2019: a 2026 tiene 7 años -> fila «desde 5»: 10 y 8
        self.assertEqual((svc.dias_asignados(self.ana, VAC, 2026, 1), svc.dias_asignados(self.ana, VAC, 2026, 2)), (10, 8))
        # Beto ingresó en 2024: 1 año en enero, 2 en julio -> fila «desde 0» de confianza: 5 y 5
        self.assertEqual((svc.dias_asignados(self.beto, VAC, 2026, 1), svc.dias_asignados(self.beto, VAC, 2026, 2)), (5, 5))

    def test_la_antiguedad_se_toma_al_inicio_de_cada_periodo(self):
        # Beto cumple 3 años el 1 de junio de 2027: en el 1.er periodo de 2027 (1 ene) aún tiene 2; en el 2.º ya 3.
        self.assertEqual(svc.dias_asignados(self.beto, VAC, 2027, 1), 5)
        self.assertEqual(svc.dias_asignados(self.beto, VAC, 2027, 2), 4)

    def test_los_economicos_son_globales_y_solo_de_sindicalizados(self):
        self.assertEqual((svc.dias_asignados(self.ana, ECO, 2026, 1), svc.dias_asignados(self.ana, ECO, 2026, 2)), (1, 2))
        self.assertEqual(svc.dias_asignados(self.beto, ECO, 2026, 1), 0)
        Configuracion.objects.filter(pk=1).update(dias_economicos_p1=3)
        self.assertEqual(svc.dias_asignados(self.cris, ECO, 2026, 1), 3)
        self.assertEqual({(f["tipo"], f["periodo"]) for f in svc.saldos(self.beto, 2026)}, {(VAC, 1), (VAC, 2)})

    def test_ajuste_por_empleado_manda_sobre_la_tabla_y_se_puede_quitar(self):
        svc.ajustar_dias(self.ana, usuario=self.control, anio=2026, periodo=1, dias=20)
        svc.ajustar_dias(self.ana, usuario=self.control, anio=2026, periodo=2, dias=10)
        self.assertEqual((svc.dias_asignados(self.ana, VAC, 2026, 1), svc.dias_asignados(self.ana, VAC, 2026, 2)), (20, 10))
        svc.quitar_ajuste(self.ana, usuario=self.control, anio=2026, periodo=1)
        self.assertEqual(svc.dias_asignados(self.ana, VAC, 2026, 1), 10)
        with self.assertRaises(ValidationError):
            svc.ajustar_dias(self.ana, usuario=self.control, anio=2026, periodo=1, dias=99)

    def test_no_se_puede_ajustar_por_debajo_de_lo_ya_solicitado(self):
        svc.crear_solicitud(self.ana, usuario=self.ana.usuario, tipo=VAC, fecha_inicio=LUNES, fecha_fin=LUNES + datetime.timedelta(days=4))
        with self.assertRaises(ValidationError):
            svc.ajustar_dias(self.ana, usuario=self.control, anio=2026, periodo=1, dias=4)


class SolicitudesTests(BasePermisos):
    def crear(self, empleado, tipo, inicio, fin, **extra):
        return svc.crear_solicitud(empleado, usuario=empleado.usuario, tipo=tipo, fecha_inicio=inicio, fecha_fin=fin, **extra)

    def test_vacaciones_solo_descuentan_lunes_a_viernes(self):
        s, _ = self.crear(self.ana, VAC, LUNES, LUNES + datetime.timedelta(days=13))  # dos semanas completas con fines de semana
        self.assertEqual((s.dias, s.anio, s.periodo, s.estatus, s.validado), (10, 2026, 1, "activa", False))
        fila = next(f for f in svc.saldos(self.ana, 2026) if f["tipo"] == VAC and f["periodo"] == 1)
        self.assertEqual((fila["asignados"], fila["usados"], fila["disponibles"]), (10, 10, 0))

    def test_no_se_puede_pedir_mas_de_lo_que_queda(self):
        self.crear(self.ana, VAC, LUNES, LUNES + datetime.timedelta(days=4))
        with self.assertRaisesMessage(ValidationError, "solo le quedan 5 de 10"):
            self.crear(self.ana, VAC, d(3, 16), d(3, 24))  # 7 días hábiles

    def test_economicos_no_pueden_incluir_sabado_ni_domingo(self):
        with self.assertRaisesMessage(ValidationError, "sábado ni domingo"):
            self.crear(self.ana, ECO, d(7, 3), d(7, 6))  # viernes a lunes
        with self.assertRaisesMessage(ValidationError, "sábado ni domingo"):
            self.crear(self.ana, ECO, d(7, 4), d(7, 4))  # sábado
        s, _ = self.crear(self.ana, ECO, d(7, 6), d(7, 7))  # lunes y martes, con 2 días en el 2.º periodo
        self.assertEqual((s.dias, s.periodo), (2, 2))

    def test_economicos_solo_para_sindicalizados(self):
        with self.assertRaisesMessage(ValidationError, "solo para el personal sindicalizado"):
            self.crear(self.beto, ECO, LUNES, LUNES)

    def test_un_periodo_no_se_puede_cruzar_ni_empalmar(self):
        with self.assertRaisesMessage(ValidationError, "mismo periodo"):
            self.crear(self.ana, VAC, d(6, 29), d(7, 2))
        with self.assertRaises(ValidationError):
            self.crear(self.ana, VAC, LUNES, LUNES - datetime.timedelta(days=1))
        self.crear(self.ana, VAC, LUNES, LUNES + datetime.timedelta(days=1))
        with self.assertRaisesMessage(ValidationError, "se empalma"):
            self.crear(self.ana, VAC, LUNES + datetime.timedelta(days=1), LUNES + datetime.timedelta(days=3))

    def test_un_rango_solo_de_fin_de_semana_no_tiene_dias_habiles(self):
        with self.assertRaisesMessage(ValidationError, "ningún día hábil"):
            self.crear(self.ana, VAC, d(3, 7), d(3, 8))

    def test_los_dias_no_usados_se_pierden_cada_periodo_y_anio_es_independiente(self):
        self.crear(self.ana, VAC, LUNES, LUNES + datetime.timedelta(days=2))
        p2 = next(f for f in svc.saldos(self.ana, 2026) if f["tipo"] == VAC and f["periodo"] == 2)
        self.assertEqual((p2["asignados"], p2["disponibles"]), (8, 8))  # lo no usado del 1.º no pasa al 2.º
        p1_2027 = next(f for f in svc.saldos(self.ana, 2027) if f["tipo"] == VAC and f["periodo"] == 1)
        self.assertEqual(p1_2027["usados"], 0)

    def test_cancelar_libera_el_saldo_y_lo_validado_solo_lo_cancela_control(self):
        s, _ = self.crear(self.ana, VAC, LUNES, LUNES + datetime.timedelta(days=4))
        with self.assertRaises(ValidationError):
            svc.cancelar_solicitud(s, usuario=self.ana.usuario, motivo="no")
        svc.validar_solicitud(s, usuario=self.control)
        with self.assertRaisesMessage(ValidationError, "pídale a control"):
            svc.cancelar_solicitud(s, usuario=self.ana.usuario, motivo="Ya no la necesito")
        svc.cancelar_solicitud(s, usuario=self.control, motivo="Cancelada a petición", es_control=True)
        self.assertEqual(svc.dias_usados(self.ana, VAC, 2026, 1), 0)
        self.crear(self.ana, VAC, LUNES, LUNES + datetime.timedelta(days=4))  # el saldo se recuperó

    def test_validar_es_un_control_que_no_cambia_el_saldo(self):
        s, _ = self.crear(self.ana, VAC, LUNES, LUNES + datetime.timedelta(days=1))
        antes = svc.dias_usados(self.ana, VAC, 2026, 1)
        svc.validar_solicitud(s, usuario=self.control)
        s.refresh_from_db()
        self.assertEqual((s.validado, s.validado_por), (True, self.control))
        self.assertEqual(svc.dias_usados(self.ana, VAC, 2026, 1), antes)
        with self.assertRaises(ValidationError):
            svc.validar_solicitud(s, usuario=self.control)
        svc.validar_solicitud(s, usuario=self.control, validado=False)
        s.refresh_from_db()
        self.assertFalse(s.validado)
        self.assertEqual([m.accion for m in s.movimientos.all()], ["solicitud", "validacion", "quitar_validacion"])

    def test_bitacora_de_solo_escritura(self):
        s, _ = self.crear(self.ana, VAC, LUNES, LUNES)
        m = s.movimientos.get()
        with self.assertRaises(ValueError):
            m.delete()


class CoberturaTests(BasePermisos):
    def crear(self, empleado, inicio, fin=None):
        return svc.crear_solicitud(empleado, usuario=empleado.usuario, tipo=VAC, fecha_inicio=inicio, fecha_fin=fin or inicio)

    def test_un_solo_ausente_de_dos_deja_uno_y_no_avisa_con_minimo_1(self):
        _, avisos = self.crear(self.beto, LUNES)
        self.assertEqual(avisos, [])

    def test_bajar_del_minimo_solo_avisa_y_registra_la_solicitud(self):
        UmbralSede.objects.create(sede_uuid=self.sede_a.pk, sede_nombre="Palacio", minimo=2)
        s, avisos = self.crear(self.beto, LUNES)
        self.assertEqual(len(avisos), 1)
        self.assertIn("por debajo del mínimo", avisos[0])
        self.assertEqual(s.bajo_umbral[0]["presentes"], 1)
        self.assertTrue(Solicitud.objects.filter(pk=s.pk, estatus="activa").exists())  # no se bloquea

    def test_los_dos_fuera_el_mismo_dia_dejan_cero_presentes(self):
        self.crear(self.ana, LUNES)
        s, avisos = self.crear(self.beto, LUNES)
        self.assertEqual(s.bajo_umbral[0]["presentes"], 0)
        self.assertTrue(avisos)

    def test_la_cobertura_indica_quien_esta_fuera_y_ignora_fines_de_semana_y_canceladas(self):
        s, _ = self.crear(self.ana, LUNES, LUNES + datetime.timedelta(days=6))
        filas = svc.cobertura(self.sede_a.pk, [LUNES + datetime.timedelta(days=n) for n in range(7)])
        self.assertEqual(len(filas), 5)  # sin sábado ni domingo
        self.assertEqual(filas[0]["fuera"][0]["nombre"], "Ana Sindicalizada")
        svc.cancelar_solicitud(s, usuario=self.control, motivo="Cancelada por prueba", es_control=True)
        self.assertEqual(svc.cobertura(self.sede_a.pk, [LUNES])[0]["fuera"], [])

    def test_sede_sin_personal_o_empleado_sin_sede_no_valida_cobertura(self):
        self.assertEqual(svc.cobertura(None, [LUNES]), [])
        self.assertEqual(svc.cobertura(uuid.uuid4(), [LUNES]), [])
