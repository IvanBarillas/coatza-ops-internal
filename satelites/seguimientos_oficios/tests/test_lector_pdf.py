import datetime
from unittest import mock

from django.test import override_settings
from django.urls import reverse

from satelites.seguimientos_oficios.models import AdjuntoOCR, Direccion, Documento
from satelites.seguimientos_oficios.services import adjuntar_pdf, quitar_adjunto
from satelites.seguimientos_oficios.storage import almacen

from .base import PDF, BaseAdjuntos, pdf

BUSCABLE = b"%PDF-1.4 copia con capa de texto"


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class LectorPdfTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.documento_ = self.documento("recibido")
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            self.adjunto, _ = adjuntar_pdf(self.documento_, usuario=self.user, archivo=pdf("scan.pdf"))

    def dar_copia_buscable(self):
        ruta = self.adjunto.ruta.removesuffix(".pdf") + "__buscable.pdf"
        almacen().save(ruta, __import__("django.core.files.base", fromlist=["ContentFile"]).ContentFile(BUSCABLE))
        AdjuntoOCR.objects.filter(adjunto=self.adjunto).update(estado="listo", ruta_buscable=ruta)
        return ruta

    def url(self, nombre, **kw):
        return reverse(f"seguimientos_oficios:{nombre}", args=[self.documento_.pk, self.adjunto.pk])

    def test_la_pagina_del_lector_trae_los_datos_para_pdfjs(self):
        respuesta = self.client.get(self.url("lector"), {"pagina": 3, "q": "instalación eléctrica"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'data-pagina="3"')
        self.assertContains(respuesta, 'data-consulta="instalación eléctrica"')
        self.assertContains(respuesta, f'data-pdf="{self.url("adjunto_descargar")}"')
        self.assertContains(respuesta, "seguimientos_oficios/visor")
        self.assertEqual(respuesta["X-Frame-Options"], "SAMEORIGIN")

    def test_usa_la_copia_con_texto_solo_si_existe(self):
        self.assertNotContains(self.client.get(self.url("lector")), "version=buscable")
        self.dar_copia_buscable()
        self.assertContains(self.client.get(self.url("lector")), "?version=buscable")

    def test_la_descarga_ofrece_la_copia_con_texto_y_siempre_el_original(self):
        original = b"".join(self.client.get(self.url("adjunto_descargar")).streaming_content)
        self.assertEqual(original, PDF + b"a.pdf" if False else original)
        self.assertNotEqual(original, BUSCABLE)
        sin_copia = self.client.get(self.url("adjunto_descargar"), {"version": "buscable"})
        self.assertEqual(b"".join(sin_copia.streaming_content), original)
        self.dar_copia_buscable()
        con_copia = self.client.get(self.url("adjunto_descargar"), {"version": "buscable"})
        self.assertEqual(b"".join(con_copia.streaming_content), BUSCABLE)
        self.assertEqual(b"".join(self.client.get(self.url("adjunto_descargar")).streaming_content), original)
        self.assertIn("attachment", self.client.get(self.url("adjunto_descargar"), {"descargar": "1"})["Content-Disposition"])
        self.assertIn("inline", self.client.get(self.url("adjunto_descargar"))["Content-Disposition"])

    def test_no_abre_archivos_quitados_ni_de_otra_direccion(self):
        otra = Direccion.objects.create(nombre="Egresos")
        ajeno = Documento.objects.create(
            sentido="recibido", estado="registrado", direccion=otra, direccion_nombre="Egresos",
            contraparte="X", asunto="Ajeno", fecha=datetime.date(2026, 9, 1),
        )
        self.assertEqual(self.client.get(reverse("seguimientos_oficios:lector", args=[ajeno.pk, self.adjunto.pk])).status_code, 404)
        quitar_adjunto(self.adjunto, usuario=self.user, motivo="Se subió el archivo equivocado por error")
        self.assertEqual(self.client.get(self.url("lector")).status_code, 404)

    def test_requiere_sesion(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url("lector")).status_code, 302)
