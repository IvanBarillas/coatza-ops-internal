import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.models import Gestor
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.services import adjuntar_pdf, crear_documento, marcar_entregado

from .base import BaseAdjuntos, pdf


class MisPendientesTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self.juan_usuario = get_user_model().objects.create_user(email="juan@example.test", first_name="Juan")
        UserAppRole.objects.create(user=self.juan_usuario, app=self.app, role="gestor", permissions_list=P.ROLE_MAPPING["gestor"])
        self.juan = Gestor.objects.create(direccion=self.direccion, nombre="Juan", usuario=self.juan_usuario)
        self.maria = Gestor.objects.create(direccion=self.direccion, nombre="María")

    def enviar(self, asunto, gestor):
        return crear_documento(
            usuario=self.user, direccion=self.direccion, sentido="enviado", clase="oficio",
            contraparte="Tesorería", asunto=asunto, fecha=datetime.date(2026, 9, 1), gestor=gestor,
        )

    def test_el_gestor_ve_solo_sus_pendientes(self):
        propio = self.enviar("Oficio de Juan", self.juan)
        ajeno = self.enviar("Oficio de María", self.maria)
        self.client.force_login(self.juan_usuario)
        respuesta = self.client.get(reverse("seguimientos_oficios:mis_pendientes"))
        self.assertContains(respuesta, "Oficio de Juan")
        self.assertNotContains(respuesta, "Oficio de María")
        self.assertEqual(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[propio.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[ajeno.pk])).status_code, 404)

    def test_el_gestor_no_accede_a_la_lista_general_ni_a_acciones(self):
        propio = self.enviar("Oficio de Juan", self.juan)
        self.client.force_login(self.juan_usuario)
        self.assertIn(self.client.get(reverse("seguimientos_oficios:documento_list")).status_code, (302, 403))
        for accion in ("entregar", "cancelar", "adjuntar", "editar"):
            url = reverse(f"seguimientos_oficios:documento_{accion}", args=[propio.pk])
            self.assertIn(self.client.post(url, {"motivo": "Registrado por error en la captura"}).status_code, (302, 403))
        propio.refresh_from_db()
        self.assertEqual(propio.estado, "generado")
        detalle = self.client.get(reverse("seguimientos_oficios:documento_detail", args=[propio.pk]))
        self.assertNotContains(detalle, "Cancelar documento")
        self.assertNotContains(detalle, "Registrar entrega")

    def test_el_menu_del_gestor_solo_tiene_mis_pendientes(self):
        self.client.force_login(self.juan_usuario)
        respuesta = self.client.get(reverse("seguimientos_oficios:mis_pendientes"))
        self.assertContains(respuesta, reverse("seguimientos_oficios:mis_pendientes"))
        self.assertNotContains(respuesta, reverse("seguimientos_oficios:documento_create"))
        self.assertNotContains(respuesta, reverse("seguimientos_oficios:catalogos"))

    def test_al_concluir_deja_de_ser_pendiente_del_gestor(self):
        documento = self.enviar("Se concluye", self.juan)
        marcar_entregado(documento, usuario=self.user, fecha_entrega=datetime.date(2026, 9, 2), receptor="R")
        self.client.force_login(self.juan_usuario)
        self.assertContains(self.client.get(reverse("seguimientos_oficios:mis_pendientes")), "Se concluye")
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            adjuntar_pdf(documento, usuario=self.user, archivo=pdf())
        self.assertNotContains(self.client.get(reverse("seguimientos_oficios:mis_pendientes")), "Se concluye")
        self.assertEqual(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk])).status_code, 404)

    def test_descarga_de_adjuntos_solo_de_sus_pendientes(self):
        entregado = self.enviar("Con archivo", self.juan)
        marcar_entregado(entregado, usuario=self.user, fecha_entrega=datetime.date(2026, 9, 2), receptor="R")
        original = self.documento("recibido")
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            ajeno, _ = adjuntar_pdf(original, usuario=self.user, archivo=pdf("otro.pdf", b"%PDF-1.4 otro"))
        self.client.force_login(self.juan_usuario)
        url = reverse("seguimientos_oficios:adjunto_descargar", args=[original.pk, ajeno.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_usuario_sin_gestor_vinculado_ve_el_aviso(self):
        Gestor.objects.filter(pk=self.juan.pk).update(usuario=None)
        self.client.force_login(self.juan_usuario)
        self.assertContains(self.client.get(reverse("seguimientos_oficios:mis_pendientes")), "no está vinculado a un gestor")

    def test_vincular_usuarios_desde_catalogos(self):
        UserAppRole.objects.filter(user=self.user).update(role="owner", permissions_list=P.ROLE_MAPPING["owner"])
        self.client.force_login(self.user)
        sin_membresia = get_user_model().objects.create_user(email="fuera@example.test")
        actualizar = reverse("seguimientos_oficios:gestor_actualizar", args=[self.maria.pk])
        self.client.post(actualizar, {"nombre": "María", "usuario": str(sin_membresia.pk)})
        self.maria.refresh_from_db()
        self.assertIsNone(self.maria.usuario)
        self.client.post(actualizar, {"nombre": "María", "usuario": str(self.juan_usuario.pk)})
        self.maria.refresh_from_db()
        self.assertIsNone(self.maria.usuario)
        editor = get_user_model().objects.create_user(email="maria@example.test", first_name="María")
        UserAppRole.objects.create(user=editor, app=self.app, role="gestor", permissions_list=P.ROLE_MAPPING["gestor"])
        self.client.post(actualizar, {"nombre": "María", "usuario": str(editor.pk)})
        self.maria.refresh_from_db()
        self.assertEqual(self.maria.usuario, editor)
        pagina = self.client.get(reverse("seguimientos_oficios:direccion_editar", args=[self.direccion.pk]))
        self.assertContains(pagina, "maria@example.test")
