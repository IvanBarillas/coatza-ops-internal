import datetime

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.permisos_personal import services as svc
from satelites.permisos_personal.models import Configuracion, Empleado, RangoAntiguedad, Solicitud, Tipo, UmbralSede
from satelites.permisos_personal.permissions import PermisosPersonalPermissions as P

from .base import LUNES, BasePermisos, d


def url(nombre, *args):
    return reverse(f"permisos_personal:{nombre}", args=args)


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class VistasPermisosTests(BasePermisos):
    def entrar(self, usuario):
        self.client.force_login(usuario)

    def negado(self, respuesta):
        self.assertIn(respuesta.status_code, (302, 403))

    # ---- entrada, menú y permisos
    def test_inicio_lleva_a_cada_rol_a_su_vista(self):
        self.entrar(self.ana.usuario)
        self.assertRedirects(self.client.get(url("inicio")), url("mis_solicitudes"), fetch_redirect_response=False)
        lector = self.usuario("lector@example.test", "viewer", "Lola", "Lectora")
        self.entrar(lector)
        self.assertRedirects(self.client.get(url("inicio")), url("calendario"), fetch_redirect_response=False)

    def test_el_menu_depende_del_rol(self):
        self.entrar(self.ana.usuario)
        self.assertEqual([i["name"] for i in self.client.get(url("mis_solicitudes")).context["sidebar_items"]], ["Mis permisos", "Nueva solicitud", "Calendario"])
        self.entrar(self.control)
        self.assertEqual(
            [i["name"] for i in self.client.get(url("calendario")).context["sidebar_items"]],
            ["Mis permisos", "Nueva solicitud", "Calendario", "Solicitudes", "Empleados", "Configuración"],
        )

    def test_el_empleado_no_entra_a_lo_de_control(self):
        self.entrar(self.ana.usuario)
        for nombre in ("solicitudes", "empleados", "empleado_crear", "configuracion"):
            self.negado(self.client.get(url(nombre)))
        solicitud, _ = svc.crear_solicitud(self.beto, usuario=self.beto.usuario, tipo=svc.VACACIONES, fecha_inicio=LUNES, fecha_fin=LUNES)
        self.negado(self.client.post(url("solicitud_validar", solicitud.pk), {"validado": "1"}))
        self.negado(self.client.post(url("solicitud_cancelar", solicitud.pk), {"motivo": "Cancelo la ajena"}))  # es de otro empleado
        solicitud.refresh_from_db()
        self.assertEqual((solicitud.validado, solicitud.estatus), (False, "activa"))

    # ---- mis permisos y nueva solicitud
    def test_quien_no_es_empleado_ve_un_aviso(self):
        sin_alta = self.usuario("sinalta@example.test", "empleado", "Sin", "Alta")
        self.entrar(sin_alta)
        self.assertContains(self.client.get(url("mis_solicitudes")), "no está dado de alta como empleado")
        self.assertContains(self.client.get(url("solicitud_crear")), "no está dado de alta")

    def test_resumen_con_saldos_por_periodo(self):
        self.entrar(self.ana.usuario)
        pagina = self.client.get(url("mis_solicitudes"), {"anio": 2026})
        filas = {(s["tipo"], s["periodo"]): (s["asignados"], s["disponibles"]) for s in pagina.context["saldos"]}
        self.assertEqual(filas, {("vacaciones", 1): (10, 10), ("vacaciones", 2): (8, 8), ("economico", 1): (1, 1), ("economico", 2): (2, 2)})
        self.entrar(self.beto.usuario)
        self.assertEqual(len(self.client.get(url("mis_solicitudes"), {"anio": 2026}).context["saldos"]), 2)  # confianza: sin económicos

    def test_crear_solicitud_avisa_si_baja_del_minimo_pero_la_registra(self):
        UmbralSede.objects.create(sede_uuid=self.sede_a.pk, sede_nombre="Palacio", minimo=2)
        self.entrar(self.ana.usuario)
        r = self.client.post(url("solicitud_crear"), {"tipo": "vacaciones", "fecha_inicio": LUNES.isoformat(), "fecha_fin": (LUNES + datetime.timedelta(days=2)).isoformat(), "comentarios": "Viaje"})
        self.assertRedirects(r, url("mis_solicitudes"), fetch_redirect_response=False)
        solicitud = Solicitud.objects.get()
        self.assertEqual((solicitud.dias, solicitud.empleado), (3, self.ana))
        textos = mensajes(r)
        self.assertTrue(any("Solicitud registrada" in t for t in textos))
        self.assertTrue(any("por debajo del mínimo" in t for t in textos))

    def test_errores_de_reglas_se_muestran_en_el_formulario(self):
        self.entrar(self.ana.usuario)
        r = self.client.post(url("solicitud_crear"), {"tipo": "economico", "fecha_inicio": d(3, 6).isoformat(), "fecha_fin": d(3, 8).isoformat()})
        self.assertContains(r, "sábado ni domingo")
        self.assertFalse(Solicitud.objects.exists())
        r = self.client.post(url("solicitud_crear"), {"tipo": "vacaciones", "fecha_inicio": d(6, 29).isoformat(), "fecha_fin": d(7, 2).isoformat()})
        self.assertContains(r, "mismo periodo")

    def test_el_de_confianza_no_ve_la_opcion_de_economicos(self):
        self.entrar(self.beto.usuario)
        pagina = self.client.get(url("solicitud_crear"))
        self.assertEqual([v for v, _ in pagina.context["form"].fields["tipo"].choices], ["vacaciones"])
        r = self.client.post(url("solicitud_crear"), {"tipo": "economico", "fecha_inicio": LUNES.isoformat()})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Solicitud.objects.exists())

    def test_cancelar_la_propia_recupera_saldo_y_lo_validado_solo_lo_cancela_control(self):
        solicitud, _ = svc.crear_solicitud(self.ana, usuario=self.ana.usuario, tipo=svc.VACACIONES, fecha_inicio=LUNES, fecha_fin=LUNES + datetime.timedelta(days=4))
        self.entrar(self.ana.usuario)
        self.client.post(url("solicitud_cancelar", solicitud.pk), {"motivo": "Cambio de planes"})
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estatus, "cancelada")
        otra, _ = svc.crear_solicitud(self.ana, usuario=self.ana.usuario, tipo=svc.VACACIONES, fecha_inicio=LUNES, fecha_fin=LUNES)
        svc.validar_solicitud(otra, usuario=self.control)
        r = self.client.post(url("solicitud_cancelar", otra.pk), {"motivo": "Ya no quiero"}, follow=True)
        self.assertContains(r, "pídale a control")
        self.entrar(self.control)
        self.client.post(url("solicitud_cancelar", otra.pk), {"motivo": "Cancelada por control"})
        otra.refresh_from_db()
        self.assertEqual(otra.estatus, "cancelada")

    # ---- control: solicitudes y validación
    def test_solicitudes_filtra_por_estado_y_control_valida_con_un_check(self):
        s1, _ = svc.crear_solicitud(self.ana, usuario=self.ana.usuario, tipo=svc.VACACIONES, fecha_inicio=LUNES, fecha_fin=LUNES)
        s2, _ = svc.crear_solicitud(self.cris, usuario=self.cris.usuario, tipo=svc.ECONOMICO, fecha_inicio=LUNES, fecha_fin=LUNES)
        self.entrar(self.control)
        pagina = self.client.get(url("solicitudes"), {"anio": 2026})
        self.assertEqual({e["clave"]: e["total"] for e in pagina.context["estados"]}, {"pendientes": 2, "validadas": 0, "canceladas": 0, "todas": 2})
        self.client.post(url("solicitud_validar", s1.pk), {"validado": "1", "volver": url("solicitudes")})
        s1.refresh_from_db()
        self.assertEqual((s1.validado, s1.validado_por), (True, self.control))
        pagina = self.client.get(url("solicitudes"), {"anio": 2026, "estado": "validadas"})
        self.assertEqual([s.pk for s in pagina.context["pagina"]], [s1.pk])
        self.assertEqual([s.pk for s in self.client.get(url("solicitudes"), {"anio": 2026, "tipo": "economico", "estado": "todas"}).context["pagina"]], [s2.pk])
        self.assertEqual([s.pk for s in self.client.get(url("solicitudes"), {"anio": 2026, "estado": "todas", "q": "cris"}).context["pagina"]], [s2.pk])
        self.assertEqual([s.pk for s in self.client.get(url("solicitudes"), {"anio": 2026, "estado": "todas", "sede": str(self.sede_b.pk)}).context["pagina"]], [s2.pk])

    def test_el_viewer_consulta_pero_no_puede_validar(self):
        s1, _ = svc.crear_solicitud(self.ana, usuario=self.ana.usuario, tipo=svc.VACACIONES, fecha_inicio=LUNES, fecha_fin=LUNES)
        lector = self.usuario("lector2@example.test", "viewer", "Lola", "Lectora")
        self.entrar(lector)
        self.assertEqual(self.client.get(url("solicitudes"), {"anio": 2026}).status_code, 200)
        self.negado(self.client.post(url("solicitud_validar", s1.pk), {"validado": "1"}))

    def test_volver_solo_acepta_rutas_del_modulo(self):
        s1, _ = svc.crear_solicitud(self.ana, usuario=self.ana.usuario, tipo=svc.VACACIONES, fecha_inicio=LUNES, fecha_fin=LUNES)
        self.entrar(self.control)
        r = self.client.post(url("solicitud_validar", s1.pk), {"validado": "1", "volver": "https://malo.example/robar"})
        self.assertEqual(r["Location"], url("solicitudes"))

    # ---- calendario
    def test_calendario_marca_los_dias_bajo_el_minimo(self):
        UmbralSede.objects.create(sede_uuid=self.sede_a.pk, sede_nombre="Palacio", minimo=2)
        svc.crear_solicitud(self.ana, usuario=self.ana.usuario, tipo=svc.VACACIONES, fecha_inicio=LUNES, fecha_fin=LUNES + datetime.timedelta(days=1))
        self.entrar(self.ana.usuario)
        pagina = self.client.get(url("calendario"), {"anio": 2026, "mes": 3})
        self.assertEqual(pagina.context["con_alertas"], 2)
        dias = {dia["fecha"]: dia for semana in pagina.context["semanas"] for dia in semana}
        self.assertEqual(dias[LUNES]["fuera"][0]["nombre"], "Ana Sindicalizada")
        self.assertEqual(dias[LUNES]["bajo"][0]["presentes"], 1)
        self.assertEqual(dias[d(3, 7)]["fuera"], [])  # sábado
        self.assertContains(pagina, "Ana Sindicalizada")
        self.assertEqual(self.client.get(url("calendario"), {"anio": 2026, "mes": 3, "sede": str(self.sede_b.pk)}).context["con_alertas"], 0)
        self.assertEqual(self.client.get(url("calendario"), {"anio": "x", "mes": "99"}).status_code, 200)  # parámetros inválidos no rompen

    # ---- empleados
    def test_alta_y_ajuste_de_empleado(self):
        nuevo = self.usuario("nuevo@example.test", "empleado", "Nora", "Nueva")
        self.entrar(self.control)
        r = self.client.post(url("empleado_crear"), {
            "usuario": nuevo.pk, "tipo": "sindicalizado", "fecha_ingreso": "2020-04-01", "sede": str(self.sede_b.pk), "activo": "on",
        })
        empleado = Empleado.objects.get(usuario=nuevo)
        self.assertRedirects(r, url("empleado_detalle", empleado.pk), fetch_redirect_response=False)
        self.assertEqual((empleado.tipo, empleado.sede_nombre), ("sindicalizado", "Tesorería"))
        self.client.post(url("empleado_detalle", empleado.pk), {"accion": "fijar", "anio": 2026, "periodo": 1, "dias": 11})
        self.client.post(url("empleado_detalle", empleado.pk), {"accion": "fijar", "anio": 2026, "periodo": 2, "dias": 12})
        self.assertEqual((svc.dias_asignados(empleado, svc.VACACIONES, 2026, 1), svc.dias_asignados(empleado, svc.VACACIONES, 2026, 2)), (11, 12))
        self.client.post(url("empleado_detalle", empleado.pk), {"accion": "quitar", "anio": 2026, "periodo": 1, "dias": 0})
        self.assertEqual(svc.dias_asignados(empleado, svc.VACACIONES, 2026, 1), svc.dias_de_tabla(empleado, 2026, 1))
        pagina = self.client.get(url("empleado_detalle", empleado.pk), {"anio": 2026})
        self.assertContains(pagina, "Ajustado")
        self.assertEqual(self.client.get(url("empleados")).status_code, 200)

    def test_no_se_repite_el_empleado_ni_se_acepta_ingreso_futuro_o_sede_falsa(self):
        self.entrar(self.control)
        base = {"usuario": self.ana.usuario.pk, "tipo": "confianza", "fecha_ingreso": "2020-01-01", "sede": ""}
        self.assertEqual(self.client.post(url("empleado_crear"), base).status_code, 200)  # ya es empleada: no aparece entre los candidatos
        nuevo = self.usuario("otro@example.test", "empleado", "Otro", "Nuevo")
        futuro = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
        self.assertContains(self.client.post(url("empleado_crear"), {**base, "usuario": nuevo.pk, "fecha_ingreso": futuro}), "no puede ser futura")
        falsa = self.client.post(url("empleado_crear"), {**base, "usuario": nuevo.pk, "sede": "no-es-una-sede"})
        self.assertEqual(falsa.status_code, 200)
        self.assertIn("sede", falsa.context["form"].errors)
        self.assertFalse(Empleado.objects.filter(usuario=nuevo).exists())

    # ---- configuración
    def test_configuracion_de_economicos_tabla_y_minimos(self):
        self.entrar(self.control)
        self.client.post(url("configuracion"), {"accion": "economicos", "dias_economicos_p1": 2, "dias_economicos_p2": 3})
        config = Configuracion.obtener()
        self.assertEqual((config.dias_economicos_p1, config.dias_economicos_p2), (2, 3))
        self.client.post(url("configuracion"), {"accion": "rango", "tipo": "confianza", "desde_anios": 10, "dias_p1": 20, "dias_p2": 10})
        self.assertEqual(RangoAntiguedad.objects.get(tipo="confianza", desde_anios=10).dias_p1, 20)
        self.client.post(url("configuracion"), {"accion": "rango", "tipo": "confianza", "desde_anios": 10, "dias_p1": 21, "dias_p2": 11})  # actualiza
        self.assertEqual(RangoAntiguedad.objects.filter(tipo="confianza", desde_anios=10).count(), 1)
        self.assertEqual(RangoAntiguedad.objects.get(tipo="confianza", desde_anios=10).dias_p2, 11)
        fila = RangoAntiguedad.objects.get(tipo="confianza", desde_anios=10)
        self.client.post(url("configuracion"), {"accion": "rango_eliminar", "id": fila.pk})
        self.assertFalse(RangoAntiguedad.objects.filter(pk=fila.pk).exists())
        self.client.post(url("configuracion"), {"accion": "umbral", "sede": str(self.sede_a.pk), "minimo": 4})
        self.assertEqual(UmbralSede.objects.get(sede_uuid=self.sede_a.pk).minimo, 4)
        self.client.post(url("configuracion"), {"accion": "umbral", "sede": "cualquiera", "minimo": 4})
        self.assertEqual(UmbralSede.objects.count(), 1)
        self.assertEqual(self.client.get(url("configuracion")).status_code, 200)

    def test_carga_parcial_htmx(self):
        self.entrar(self.control)
        parcial = self.client.get(url("empleados"), HTTP_HX_REQUEST="true", HTTP_HX_TARGET="page-content")
        self.assertNotContains(parcial, "<html")
        self.assertContains(parcial, "Empleados")
