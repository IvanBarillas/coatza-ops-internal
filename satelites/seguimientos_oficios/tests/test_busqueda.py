import datetime
from unittest import mock

from django.urls import reverse

from satelites.seguimientos_oficios.models import AdjuntoOCR, Direccion, Documento
from satelites.seguimientos_oficios.services import adjuntar_pdf, crear_documento, marcar_entregado

from .base import BaseAdjuntos, pdf


class BusquedaTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def nuevo(self, asunto, sentido="enviado", fecha=datetime.date(2026, 9, 1), clase="oficio", contraparte="Tesorería"):
        return crear_documento(
            usuario=self.user, direccion=self.direccion, sentido=sentido, clase=clase,
            contraparte=contraparte, asunto=asunto, fecha=fecha,
        )

    def buscar(self, **parametros):
        respuesta = self.client.get(reverse("seguimientos_oficios:documento_list"), parametros)
        self.assertEqual(respuesta.status_code, 200)
        return respuesta

    def test_busca_por_asunto_folio_y_contraparte(self):
        self.nuevo("Alta de servidores", contraparte="Contraloría")
        self.nuevo("Vale de laptops")
        self.assertContains(self.buscar(q="servidores"), "Alta de servidores")
        self.assertNotContains(self.buscar(q="servidores"), "Vale de laptops")
        self.assertContains(self.buscar(q="contraloría"), "Alta de servidores")
        self.assertContains(self.buscar(q="IN-002"), "Vale de laptops")

    def test_varios_terminos_se_combinan_con_y(self):
        self.nuevo("Alta de servidores")
        self.nuevo("Alta de laptops")
        respuesta = self.buscar(q="alta laptops")
        self.assertContains(respuesta, "Alta de laptops")
        self.assertNotContains(respuesta, "Alta de servidores")

    def test_busca_dentro_del_texto_ocr(self):
        documento = self.nuevo("Documento escaneado", sentido="recibido")
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            adjunto, _ = adjuntar_pdf(documento, usuario=self.user, archivo=pdf())
        ocr = AdjuntoOCR.objects.get(adjunto=adjunto)
        ocr.estado, ocr.texto = "listo", "Se solicita el dictamen del rack número 7"
        ocr.save()
        self.nuevo("Trámite sin relación")
        respuesta = self.buscar(q="rack")
        self.assertContains(respuesta, "Documento escaneado")
        self.assertNotContains(respuesta, "Trámite sin relación")

    def test_filtros_por_sentido_estado_clase_y_fechas(self):
        enviado = self.nuevo("Enviado de septiembre")
        marcar_entregado(enviado, usuario=self.user, fecha_entrega=datetime.date(2026, 9, 2), receptor="X")
        self.nuevo("Recibido de agosto", sentido="recibido", fecha=datetime.date(2026, 8, 15), clase="comunicado")
        self.assertNotContains(self.buscar(sentido="recibido", tab="todos"), "Enviado de septiembre")
        self.assertContains(self.buscar(estado="entregado", tab="todos"), "Enviado de septiembre")
        self.assertNotContains(self.buscar(estado="entregado", tab="todos"), "Recibido de agosto")
        self.assertContains(self.buscar(clase="comunicado", tab="todos"), "Recibido de agosto")
        rango = self.buscar(desde="2026-09-01", hasta="2026-09-30", tab="todos")
        self.assertContains(rango, "Enviado de septiembre")
        self.assertNotContains(rango, "Recibido de agosto")

    def test_no_muestra_documentos_de_direcciones_no_visibles(self):
        ajena = Direccion.objects.create(nombre="Egresos")
        Documento.objects.create(
            sentido="recibido", estado="registrado", direccion=ajena, direccion_nombre="Egresos",
            contraparte="X", asunto="Secreto de Egresos", fecha=datetime.date(2026, 9, 1),
        )
        self.assertNotContains(self.buscar(q="secreto"), "Secreto de Egresos")

    def test_paginacion_conserva_los_filtros(self):
        for numero in range(30):
            self.nuevo(f"Serie {numero}", sentido="recibido", clase="comunicado")
        respuesta = self.buscar(clase="comunicado", tab="todos")
        self.assertContains(respuesta, "30 documentos")
        self.assertContains(respuesta, "tab=todos&amp;pagina=2")
        self.assertEqual(len(self.buscar(clase="comunicado", tab="todos", pagina=2).context["pagina"]), 5)

    def test_filtros_invalidos_no_rompen_la_lista(self):
        self.nuevo("Sigue apareciendo")
        self.assertContains(self.buscar(desde="no-es-fecha", estado="inventado"), "Sigue apareciendo")

    def test_busqueda_ignora_acentos_y_mayusculas_en_datos_y_ocr(self):
        self.nuevo("Reparación urgente", contraparte="Tesorería Municipal")
        documento = self.nuevo("Documento escaneado", sentido="recibido")
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            adjunto, _ = adjuntar_pdf(documento, usuario=self.user, archivo=pdf())
        ocr = AdjuntoOCR.objects.get(adjunto=adjunto)
        ocr.estado, ocr.texto = "listo", "Requerimiento de instalación eléctrica"
        ocr.save()
        for consulta in ("REPARACION", "reparación", "tesoreria"):
            self.assertContains(self.buscar(q=consulta), "Reparación urgente")
        self.assertContains(self.buscar(q="instalacion electrica"), "Documento escaneado")
        self.assertContains(self.buscar(q="INSTALACIÓN"), "Documento escaneado")

    def test_editar_actualiza_lo_que_se_busca(self):
        from satelites.seguimientos_oficios.services import editar_documento

        documento = self.nuevo("Asunto original")
        editar_documento(documento, usuario=self.user, cambios={"asunto": "Cotización de cámaras"})
        self.assertContains(self.buscar(q="camaras"), "Cotización de cámaras")
        self.assertNotContains(self.buscar(q="original"), "Asunto original")
