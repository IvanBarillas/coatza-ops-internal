import datetime
from unittest import mock

from django.urls import reverse

from apps.security.models import UserAppRole
from satelites.seguimientos_oficios.models import AdjuntoOCR, Direccion, Documento
from satelites.seguimientos_oficios.permissions import SeguimientosOficiosPermissions as P
from satelites.seguimientos_oficios.services import adjuntar_pdf, crear_documento

from .base import BaseAdjuntos, pdf

TEXTO = "Portada del oficio\fSegunda hoja sin novedades\fTercera hoja: se solicita la instalación eléctrica del rack"


class BusquedaVisorTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def con_ocr(self, asunto="Solicitud de rack", texto=TEXTO):
        documento = crear_documento(
            usuario=self.user, direccion=self.direccion, sentido="recibido", clase="oficio",
            contraparte="Proveedor", asunto=asunto, fecha=datetime.date(2026, 9, 1),
        )
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            adjunto, _ = adjuntar_pdf(documento, usuario=self.user, archivo=pdf(f"{asunto}.pdf", b"%PDF-1.4 " + asunto.encode()))
        ocr = AdjuntoOCR.objects.get(adjunto=adjunto)
        ocr.estado, ocr.texto = "listo", texto
        ocr.save()
        return documento, adjunto

    def buscar(self, **parametros):
        return self.client.get(reverse("seguimientos_oficios:busqueda"), parametros)

    def test_muestra_pagina_y_fragmento_resaltado_sin_importar_acentos(self):
        documento, adjunto = self.con_ocr()
        respuesta = self.buscar(q="INSTALACION electrica")
        self.assertContains(respuesta, "Pág. 3")
        self.assertContains(respuesta, "<mark>instalación</mark>")
        self.assertContains(respuesta, reverse("seguimientos_oficios:visor", args=[documento.pk, adjunto.pk]) + "?pagina=3")
        self.assertContains(respuesta, 'id="visor"')

    def test_coincidencia_solo_en_datos_ofrece_ver_el_pdf(self):
        self.con_ocr(asunto="Cotización de cámaras", texto="Texto sin la palabra buscada")
        respuesta = self.buscar(q="camaras")
        self.assertContains(respuesta, "Coincide en los datos del documento")
        self.assertContains(respuesta, "Ver el PDF")

    def test_sin_texto_o_sin_resultados(self):
        self.assertContains(self.buscar(), "Escribe una palabra")
        self.assertContains(self.buscar(q="inexistente"), "Sin resultados")

    def test_no_muestra_resultados_de_otras_direcciones(self):
        otra = Direccion.objects.create(nombre="Egresos")
        ajeno = Documento.objects.create(
            sentido="recibido", estado="registrado", direccion=otra, direccion_nombre="Egresos",
            contraparte="X", asunto="Asunto secreto de rack", fecha=datetime.date(2026, 9, 1),
        )
        self.assertNotContains(self.buscar(q="secreto"), "Asunto secreto")
        self.con_ocr()
        self.assertEqual(self.client.get(reverse("seguimientos_oficios:visor", args=[ajeno.pk, ajeno.pk])).status_code, 404)

    def test_visor_abre_en_la_pagina_con_el_termino(self):
        documento, adjunto = self.con_ocr()
        url = reverse("seguimientos_oficios:visor", args=[documento.pk, adjunto.pk])
        respuesta = self.client.get(url, {"pagina": 3, "q": "instalación eléctrica"}, headers={"HX-Request": "true"})
        lector = reverse("seguimientos_oficios:lector", args=[documento.pk, adjunto.pk])
        self.assertContains(respuesta, "<iframe")
        self.assertContains(respuesta, f"{lector}?pagina=3&amp;q=instalaci%C3%B3n+el%C3%A9ctrica")
        self.assertContains(respuesta, "Descargar PDF")
        self.assertContains(self.client.get(url, {"pagina": "abc"}), f"{lector}?pagina=1")

    def test_el_pdf_puede_mostrarse_en_un_iframe_del_mismo_sitio(self):
        documento, adjunto = self.con_ocr()
        respuesta = self.client.get(reverse("seguimientos_oficios:adjunto_descargar", args=[documento.pk, adjunto.pk]))
        self.assertEqual(respuesta["X-Frame-Options"], "SAMEORIGIN")

    def test_rol_de_seguimiento_no_busca_en_los_documentos(self):
        UserAppRole.objects.filter(user=self.user).update(role="seguimiento", permissions_list=P.ROLE_MAPPING["seguimiento"])
        self.assertIn(self.buscar(q="rack").status_code, (302, 403))

    def test_paginacion_conserva_la_consulta(self):
        for n in range(16):
            self.con_ocr(asunto=f"Requerimiento {n}", texto="rack")
        respuesta = self.buscar(q="rack")
        self.assertContains(respuesta, "16 documentos")
        self.assertContains(respuesta, "q=rack&amp;pagina=2")
