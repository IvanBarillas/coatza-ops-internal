import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.security.models import AreaOperativa, Dependencia, Sede, UserAppRole, UserProfile
from satelites.seguimientos_oficios.models import Direccion, Documento, Gestor
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.selectors import color_semaforo
from satelites.seguimientos_oficios.services import adjuntar_pdf, crear_documento, marcar_entregado

from .base import BaseAdjuntos, pdf


class SemaforoTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self.juan = self.gestor("Juan")
        self.observador = get_user_model().objects.create_user(email="ve@example.test")
        area = AreaOperativa.objects.create(nombre="Oficina 2", dependencia=self.dep, sede_fisica=Sede.objects.first())
        UserProfile.objects.create(user=self.observador, area=area)
        UserAppRole.objects.create(
            user=self.observador, app=self.app, role="seguimiento", permissions_list=P.ROLE_MAPPING["seguimiento"]
        )
        self.client.force_login(self.observador)

    def enviar(self, asunto, gestor=None, dias=0):
        documento = crear_documento(
            usuario=self.user, direccion=self.direccion, sentido="enviado", clase="oficio",
            contraparte="Tesorería", asunto=asunto, fecha=datetime.date(2026, 9, 1), gestor=gestor,
        )
        Documento.objects.filter(pk=documento.pk).update(created_at=timezone.now() - datetime.timedelta(days=dias))
        return Documento.objects.get(pk=documento.pk)

    def seguimiento(self, **parametros):
        return self.client.get(reverse("seguimientos_oficios:seguimiento"), parametros)

    def test_colores_por_antiguedad(self):
        self.assertEqual([color_semaforo(d) for d in (0, 6, 7, 14, 15, 40)], ["verde", "verde", "ambar", "ambar", "rojo", "rojo"])

    def test_tablero_separa_por_entregar_y_sin_evidencia_y_cuenta_colores(self):
        self.enviar("Recién generado", self.juan, dias=1)
        self.enviar("Atrasado sin gestor", None, dias=20)
        entregado = self.enviar("Entregado sin evidencia", self.juan, dias=9)
        marcar_entregado(entregado, usuario=self.user, fecha_entrega=datetime.date.today() - datetime.timedelta(days=8), receptor="Recepción")
        respuesta = self.seguimiento()
        columnas = {c["titulo"]: [d.asunto for d in c["documentos"]] for c in respuesta.context["columnas"]}
        self.assertEqual(columnas["Por entregar"], ["Atrasado sin gestor", "Recién generado"])
        self.assertEqual(columnas["Entregados sin evidencia"], ["Entregado sin evidencia"])
        self.assertEqual({s["clave"]: s["total"] for s in respuesta.context["semaforos"]}, {"rojo": 1, "ambar": 1, "verde": 1})
        self.assertContains(respuesta, "Lo trae Juan")
        self.assertContains(respuesta, "Sin gestor")

    def test_no_aparecen_concluidos_cancelados_ni_recibidos(self):
        concluido = self.enviar("Concluido")
        Documento.objects.filter(pk=concluido.pk).update(estado="concluido")
        cancelado = self.enviar("Cancelado")
        Documento.objects.filter(pk=cancelado.pk).update(estado="cancelado")
        recibido = crear_documento(
            usuario=self.user, direccion=self.direccion, sentido="recibido", clase="oficio",
            contraparte="X", asunto="Recibido", fecha=datetime.date(2026, 9, 1),
        )
        self.enviar("Pendiente real")
        respuesta = self.seguimiento()
        self.assertEqual(sum(len(c["documentos"]) for c in respuesta.context["columnas"]), 1)
        self.assertNotContains(respuesta, "Concluido</a>")
        self.assertTrue(recibido.pk)

    def test_filtros_por_semaforo_y_por_gestor(self):
        self.enviar("Rojo de Juan", self.juan, dias=30)
        self.enviar("Verde sin gestor", None, dias=0)
        solo_rojo = self.seguimiento(semaforo="rojo")
        self.assertContains(solo_rojo, "Rojo de Juan")
        self.assertNotContains(solo_rojo, "Verde sin gestor")
        self.assertContains(self.seguimiento(gestor="sin"), "Verde sin gestor")
        self.assertNotContains(self.seguimiento(gestor="sin"), "Rojo de Juan")
        self.assertContains(self.seguimiento(gestor=str(self.juan.pk)), "Rojo de Juan")
        self.assertContains(self.seguimiento(gestor="no-es-uuid", semaforo="invalido"), "Rojo de Juan")

    def test_al_subir_la_evidencia_sale_del_seguimiento(self):
        documento = self.enviar("Se concluye", self.juan)
        marcar_entregado(documento, usuario=self.user, fecha_entrega=datetime.date.today(), receptor="R")
        self.assertContains(self.seguimiento(), "Se concluye")
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            adjuntar_pdf(documento, usuario=self.user, archivo=pdf())
        self.assertNotContains(self.seguimiento(), "Se concluye")

    def test_solo_ve_las_direcciones_de_su_alcance(self):
        otra = Direccion.objects.create(nombre="Egresos", dependencia_uuid=Dependencia.objects.create(nombre="Egresos").pk, folio_manual=False)
        Documento.objects.create(
            sentido="enviado", estado="generado", direccion=otra, direccion_nombre="Egresos", folio="EG-1",
            contraparte="X", asunto="Ajeno de Egresos", fecha=datetime.date(2026, 9, 1),
        )
        self.enviar("Propio")
        respuesta = self.seguimiento()
        self.assertContains(respuesta, "Propio")
        self.assertNotContains(respuesta, "Ajeno de Egresos")

    def test_el_rol_de_seguimiento_ve_el_detalle_pero_no_actua_ni_lista_todo(self):
        documento = self.enviar("Para revisar")
        detalle = self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk]))
        self.assertEqual(detalle.status_code, 200)
        self.assertNotContains(detalle, "Registrar entrega")
        self.assertNotContains(detalle, "Cancelar documento")
        self.assertIn(self.client.get(reverse("seguimientos_oficios:documento_list")).status_code, (302, 403))
        for accion in ("entregar", "cancelar", "editar"):
            respuesta = self.client.post(reverse(f"seguimientos_oficios:documento_{accion}", args=[documento.pk]), {})
            self.assertIn(respuesta.status_code, (302, 403))
        menu = self.seguimiento()
        self.assertContains(menu, reverse("seguimientos_oficios:seguimiento"))
        self.assertNotContains(menu, reverse("seguimientos_oficios:documento_create"))

    def test_un_concluido_deja_de_abrirse_para_ese_rol(self):
        documento = self.enviar("Ya concluido")
        Documento.objects.filter(pk=documento.pk).update(estado="concluido")
        self.assertEqual(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk])).status_code, 404)

    def test_usuario_sin_permiso_no_entra(self):
        UserAppRole.objects.filter(user=self.observador).update(role="x", permissions_list=["has_access_module"])
        self.assertIn(self.seguimiento().status_code, (302, 403))


class DiasPendientesTests(BaseAdjuntos):
    def test_los_dias_se_cuentan_con_la_fecha_local_no_la_utc(self):
        from zoneinfo import ZoneInfo

        from django.test import override_settings

        documento = crear_documento(
            usuario=self.user, direccion=self.direccion, sentido="enviado", clase="oficio",
            contraparte="X", asunto="Y", fecha=datetime.date(2026, 9, 1),
        )
        with override_settings(TIME_ZONE="America/Mexico_City"):
            timezone.activate(ZoneInfo("America/Mexico_City"))
            self.addCleanup(timezone.deactivate)
            # 22:00 del 20/sep en México = 04:00 UTC del 21/sep
            registro = datetime.datetime(2026, 9, 21, 4, 0, tzinfo=datetime.timezone.utc)
            Documento.objects.filter(pk=documento.pk).update(created_at=registro)
            documento.refresh_from_db()
            with mock.patch("django.utils.timezone.localdate", return_value=datetime.date(2026, 9, 24)):
                self.assertEqual(documento.dias_pendiente, 4)
