import datetime

from django.urls import reverse

from apps.security.models import Dependencia
from satelites.seguimientos_oficios.models import Direccion, Documento
from satelites.seguimientos_oficios.services import crear_documento

from .base import BaseAdjuntos


class ContraparteTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self.egresos = Dependencia.objects.create(nombre="Egresos")
        self.client.force_login(self.user)
        self.url = reverse("seguimientos_oficios:documento_create")

    def datos(self, **extra):
        base = {
            "sentido": "enviado", "clase": "oficio", "direccion": str(self.direccion.pk), "fecha": "2026-09-02",
            "asunto": "Solicitud", "contraparte_dependencia": str(self.egresos.pk), "contraparte": "",
        }
        base.update(extra)
        return base

    def test_formulario_con_una_sola_direccion_no_la_pregunta(self):
        respuesta = self.client.get(self.url)
        self.assertFalse(respuesta.context["form"].mostrar_direccion)
        self.assertNotContains(respuesta, "Dirección que envía")
        self.assertContains(respuesta, f'name="direccion" value="{self.direccion.pk}"')
        self.assertContains(respuesta, "Egresos".upper())

    def test_con_varias_direcciones_la_pregunta(self):
        otra = Direccion.objects.create(nombre="Otra", dependencia_uuid=self.dep.pk)
        self.assertTrue(self.client.get(self.url).context["form"].mostrar_direccion)
        self.assertTrue(otra.pk)

    def test_enviado_a_una_direccion_guarda_nombre_y_vinculo(self):
        self.client.post(self.url, self.datos())
        documento = Documento.objects.get(asunto="Solicitud")
        self.egresos.refresh_from_db()
        self.assertEqual((documento.contraparte, documento.contraparte_dependencia_uuid), (self.egresos.nombre, self.egresos.pk))

    def test_recibido_de_cualquier_direccion_de_la_lista_completa(self):
        respuesta = self.client.post(self.url, self.datos(sentido="recibido", asunto="Nos envían", folio="EG/12/2026"))
        self.assertEqual(respuesta.status_code, 302)
        documento = Documento.objects.get(asunto="Nos envían")
        self.assertEqual((documento.sentido, documento.contraparte_dependencia_uuid), ("recibido", self.egresos.pk))

    def test_externa_exige_nombre_y_no_guarda_vinculo(self):
        self.client.post(self.url, self.datos(contraparte_dependencia="", contraparte="  "))
        self.assertFalse(Documento.objects.filter(asunto="Solicitud").exists())
        self.client.post(self.url, self.datos(contraparte_dependencia="", contraparte="Comisión Estatal"))
        documento = Documento.objects.get(asunto="Solicitud")
        self.assertEqual((documento.contraparte, documento.contraparte_dependencia_uuid), ("Comisión Estatal", None))

    def test_no_se_puede_enviar_a_la_propia_direccion_ni_con_dependencia_inventada(self):
        self.client.post(self.url, self.datos(contraparte_dependencia=str(self.dep.pk)))
        self.client.post(self.url, self.datos(contraparte_dependencia="11111111-1111-1111-1111-111111111111"))
        self.assertFalse(Documento.objects.filter(asunto="Solicitud").exists())

    def test_editar_cambia_la_contraparte_y_el_historial_muestra_solo_el_nombre(self):
        documento = crear_documento(
            usuario=self.user, direccion=self.direccion, sentido="enviado", clase="oficio",
            contraparte="Externo", asunto="Editable", fecha=datetime.date(2026, 9, 1),
        )
        url = reverse("seguimientos_oficios:documento_editar", args=[documento.pk])
        self.client.post(url, {
            "contraparte_dependencia": str(self.egresos.pk), "contraparte": "", "asunto": "Editable",
            "fecha": "2026-09-01", "motivo": "Era de Egresos",
        })
        documento.refresh_from_db()
        self.egresos.refresh_from_db()
        self.assertEqual((documento.contraparte, documento.contraparte_dependencia_uuid), (self.egresos.nombre, self.egresos.pk))
        cambios = documento.historial.last().datos["cambios"]
        self.assertEqual(set(cambios), {"contraparte"})
        self.assertEqual(cambios["contraparte"], {"antes": "Externo", "despues": self.egresos.nombre})
        self.assertContains(self.client.get(url), "Dirección destinataria")

    def test_detalle_etiqueta_destinatario_o_remitente(self):
        enviado = crear_documento(
            usuario=self.user, direccion=self.direccion, sentido="enviado", clase="oficio",
            contraparte="X", asunto="A", fecha=datetime.date(2026, 9, 1),
        )
        recibido = crear_documento(
            usuario=self.user, direccion=self.direccion, sentido="recibido", clase="oficio",
            contraparte="X", asunto="B", fecha=datetime.date(2026, 9, 1),
        )
        self.assertContains(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[enviado.pk])), "Destinatario")
        self.assertContains(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[recibido.pk])), "Remitente")

    def test_al_registrar_lleva_al_detalle_para_adjuntar_el_archivo(self):
        respuesta = self.client.post(self.url, self.datos(sentido="recibido", asunto="Recién llegado", folio="EG/1/2026"))
        documento = Documento.objects.get(asunto="Recién llegado")
        self.assertRedirects(respuesta, reverse("seguimientos_oficios:documento_detail", args=[documento.pk]))
        self.assertContains(self.client.get(respuesta.url), "Subir")

    def test_el_registro_no_pide_director_y_lo_captura_solo(self):
        self.assertNotIn("director_nombre", self.client.get(self.url).context["form"].fields)
        self.assertNotContains(self.client.get(self.url), "Director")
        self.client.post(self.url, self.datos(asunto="Con director automático"))
        self.assertTrue(Documento.objects.filter(asunto="Con director automático").exists())
