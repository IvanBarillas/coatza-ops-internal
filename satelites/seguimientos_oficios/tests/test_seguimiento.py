import datetime

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.models import Direccion, Gestor
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.services import cancelar_documento, crear_documento, editar_documento, marcar_entregado

from .base import BaseAdjuntos


class SeguimientoTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self.juan = Gestor.objects.create(direccion=self.direccion, nombre="Juan")
        self.maria = Gestor.objects.create(direccion=self.direccion, nombre="María")
        self.client.force_login(self.user)

    def enviar(self, asunto, gestor=None, sentido="enviado"):
        return crear_documento(
            usuario=self.user, direccion=self.direccion, sentido=sentido, clase="oficio",
            contraparte="Tesorería", asunto=asunto, fecha=datetime.date(2026, 9, 1), gestor=gestor,
        )

    def lista(self, **parametros):
        return self.client.get(reverse("seguimientos_oficios:documento_list"), parametros)

    def test_pendientes_es_la_pestana_por_defecto_y_oculta_concluidos_y_recibidos(self):
        pendiente = self.enviar("Pendiente de Juan", self.juan)
        concluido = self.enviar("Ya concluido")
        type(concluido).objects.filter(pk=concluido.pk).update(estado="concluido")
        self.enviar("Recibido registrado", sentido="recibido")
        respuesta = self.lista()
        self.assertContains(respuesta, "Pendiente de Juan")
        self.assertNotContains(respuesta, "Ya concluido")
        self.assertNotContains(respuesta, "Recibido registrado")
        self.assertEqual(respuesta.context["tab"], "pendientes")
        self.assertEqual({t["clave"]: t["total"] for t in respuesta.context["tabs"]},
                         {"pendientes": 1, "concluidos": 2, "cancelados": 0, "todos": 3})

    def test_buscar_texto_sin_pestana_explicita_busca_en_todos(self):
        concluido = self.enviar("Dictamen concluido de servidores")
        type(concluido).objects.filter(pk=concluido.pk).update(estado="concluido")
        self.assertContains(self.lista(q="servidores"), "Dictamen concluido de servidores")
        self.assertNotContains(self.lista(q="servidores", tab="pendientes"), "Dictamen concluido de servidores")

    def test_resumen_por_gestor_cuenta_pendientes_y_filtra(self):
        for asunto in ("Trámite alfa uno", "Trámite alfa dos"):
            self.enviar(asunto, self.juan)
        self.enviar("Trámite beta", self.maria)
        self.enviar("Sin nadie")
        resumen = {g["nombre"]: g["total"] for g in self.lista().context["gestores_resumen"]}
        self.assertEqual(resumen, {"Juan": 2, "María": 1, "Sin gestor": 1})
        filtrada = self.lista(gestor=str(self.juan.pk))
        self.assertContains(filtrada, "Trámite alfa uno")
        self.assertNotContains(filtrada, "Trámite beta")
        self.assertContains(self.lista(gestor="sin"), "Sin nadie")
        self.assertNotContains(self.lista(gestor="sin"), "Trámite alfa uno")

    def test_pendientes_salen_del_mas_antiguo_y_muestran_dias(self):
        primero = self.enviar("Primero")
        segundo = self.enviar("Segundo")
        marcar_entregado(primero, usuario=self.user, fecha_entrega=datetime.date(2026, 9, 2), receptor="R")
        orden = [d.asunto for d in self.lista().context["pagina"]]
        self.assertEqual(orden, ["Primero", "Segundo"])
        primero.refresh_from_db()
        self.assertGreaterEqual(primero.dias_pendiente, 0)
        self.assertIsNone(self.enviar("Recibido", sentido="recibido").dias_pendiente)

    def test_cancelados_y_concluidos_no_cuentan_como_pendientes(self):
        documento = self.enviar("A cancelar", self.juan)
        cancelar_documento(documento, usuario=self.user, motivo="Registrado por error en la captura")
        self.assertEqual(self.lista().context["gestores_resumen"], [])
        self.assertContains(self.lista(tab="cancelados"), "A cancelar")

    def test_gestor_debe_ser_de_la_direccion_activo_y_solo_en_enviados(self):
        otra = Direccion.objects.create(nombre="Egresos")
        ajeno = Gestor.objects.create(direccion=otra, nombre="Pedro")
        with self.assertRaises(ValidationError):
            self.enviar("X", ajeno)
        with self.assertRaises(ValidationError):
            self.enviar("X", self.juan, sentido="recibido")
        Gestor.objects.filter(pk=self.juan.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            self.enviar("X", Gestor.objects.get(pk=self.juan.pk))

    def test_reasignar_gestor_deja_historial(self):
        documento = self.enviar("Se lo lleva otro", self.juan)
        editar_documento(documento, usuario=self.user, cambios={"gestor": self.maria})
        documento.refresh_from_db()
        self.assertEqual(documento.gestor, self.maria)
        self.assertEqual(documento.historial.last().datos["cambios"]["gestor"], {"antes": "Juan", "despues": "María"})
        self.assertEqual(documento.historial.first().datos["gestor"], "Juan")

    def test_formulario_de_registro_asigna_gestor(self):
        respuesta = self.client.post(reverse("seguimientos_oficios:documento_create"), {
            "sentido": "enviado", "clase": "oficio", "direccion": str(self.direccion.pk), "fecha": "2026-09-02",
            "contraparte": "Tesorería", "asunto": "Con gestor", "gestor": str(self.juan.pk),
        })
        self.assertEqual(respuesta.status_code, 302)
        detalle = self.client.get(respuesta.url)
        self.assertContains(detalle, "Juan")

    def test_gestores_se_administran_solo_con_permiso_de_catalogos(self):
        crear = reverse("seguimientos_oficios:gestor_crear", args=[self.direccion.pk])
        self.client.post(crear, {"nombre": "Intruso"})
        self.assertFalse(Gestor.objects.filter(nombre="Intruso").exists())
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])
        self.client.post(crear, {"nombre": "  Ana   López "})
        self.assertTrue(Gestor.objects.filter(nombre="Ana López").exists())
        self.client.post(crear, {"nombre": "ana lópez"})
        self.assertEqual(Gestor.objects.filter(direccion=self.direccion, nombre__iexact="ana lópez").count(), 1)
        ana = Gestor.objects.get(nombre="Ana López")
        self.client.post(reverse("seguimientos_oficios:gestor_actualizar", args=[ana.pk]), {"accion": "estado"})
        ana.refresh_from_db()
        self.assertFalse(ana.is_active)
        self.assertContains(self.client.get(reverse("seguimientos_oficios:direccion_editar", args=[self.direccion.pk])), "Ana López")
