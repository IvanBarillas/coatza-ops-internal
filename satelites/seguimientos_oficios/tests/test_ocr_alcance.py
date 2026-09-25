import datetime
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.urls import reverse

from satelites.seguimientos_oficios.models import AdjuntoOCR
from satelites.seguimientos_oficios.services import adjuntar_pdf, crear_documento

from .base import BaseAdjuntos, pdf


class OcrAlcanceTests(BaseAdjuntos):
    def adjuntar(self, documento, nombre, rol=None):
        """Adjunta con la cola simulada y ejecuta los on_commit dentro del mismo parche."""
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea") as encolar:
            with self.captureOnCommitCallbacks(execute=True):
                adjunto, _ = adjuntar_pdf(documento, usuario=self.user, archivo=pdf(nombre, b"%PDF-1.4 " + nombre.encode()), rol=rol)
        return adjunto, encolar

    def test_solo_original_y_firmado_pasan_por_ocr(self):
        original, encolar = self.adjuntar(self.documento("recibido"), "r.pdf")
        self.assertEqual(original.ocr.estado, "pendiente")
        encolar.assert_called_once()
        enviado = self.documento()
        firmado, _ = self.adjuntar(enviado, "f.pdf")
        self.assertTrue(AdjuntoOCR.objects.filter(adjunto=firmado).exists())
        from satelites.seguimientos_oficios.services import marcar_entregado

        marcar_entregado(enviado, usuario=self.user, fecha_entrega=datetime.date(2026, 9, 2), receptor="R")
        acuse, encolar = self.adjuntar(enviado, "acuse.pdf")
        self.assertEqual(acuse.rol, "evidencia")
        self.assertFalse(AdjuntoOCR.objects.filter(adjunto=acuse).exists())
        encolar.assert_not_called()

    def test_el_detalle_indica_que_el_acuse_no_lleva_ocr(self):
        from satelites.seguimientos_oficios.services import marcar_entregado

        documento = self.entregado()
        self.adjuntar(documento, "acuse.pdf")
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("seguimientos_oficios:documento_detail", args=[documento.pk])), "Acuse: sin OCR")

    def test_el_texto_de_un_acuse_antiguo_no_entra_a_la_busqueda(self):
        documento = self.entregado()
        acuse, _ = self.adjuntar(documento, "acuse.pdf")
        AdjuntoOCR.objects.create(adjunto=acuse, estado="listo", texto="palabra rarisima zorzal")
        self.client.force_login(self.user)
        respuesta = self.client.get(reverse("seguimientos_oficios:busqueda"), {"q": "zorzal"})
        self.assertContains(respuesta, "Sin resultados")

    def test_reprocesar_no_toca_los_acuses(self):
        documento = self.entregado()
        acuse, _ = self.adjuntar(documento, "acuse.pdf")
        AdjuntoOCR.objects.create(adjunto=acuse)
        with mock.patch("satelites.seguimientos_oficios.ocr.extraer_texto") as motor:
            call_command("oficios_reprocesar_ocr", stdout=StringIO())
        motor.assert_not_called()
        self.assertEqual(AdjuntoOCR.objects.get(adjunto=acuse).estado, "pendiente")


class BuscarEnTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        for sentido, asunto in (("recibido", "Oficio recibido de prueba"), ("enviado", "Oficio enviado de prueba")):
            crear_documento(
                usuario=self.user, direccion=self.direccion, sentido=sentido, clase="oficio",
                contraparte="X", asunto=asunto, fecha=datetime.date(2026, 9, 1),
            )

    def buscar(self, **extra):
        return self.client.get(reverse("seguimientos_oficios:busqueda"), {"q": "prueba", **extra})

    def test_todos_recibidos_y_enviados(self):
        todos = self.buscar()
        self.assertContains(todos, "Oficio recibido de prueba")
        self.assertContains(todos, "Oficio enviado de prueba")
        solo_recibidos = self.buscar(sentido="recibido")
        self.assertContains(solo_recibidos, "Oficio recibido de prueba")
        self.assertNotContains(solo_recibidos, "Oficio enviado de prueba")
        solo_enviados = self.buscar(sentido="enviado")
        self.assertContains(solo_enviados, "Oficio enviado de prueba")
        self.assertNotContains(solo_enviados, "Oficio recibido de prueba")
        self.assertContains(self.buscar(sentido="invalido"), "Oficio recibido de prueba")

    def test_los_enlaces_de_ambito_conservan_la_consulta(self):
        respuesta = self.buscar(sentido="enviado")
        self.assertContains(respuesta, "q=prueba&amp;sentido=recibido")
        self.assertEqual({a["clave"]: a["activo"] for a in respuesta.context["ambitos"]},
                         {"": False, "recibido": False, "enviado": True})
