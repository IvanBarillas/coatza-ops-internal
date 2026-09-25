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


class FiltrosDeBusquedaTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.creados = {}
        for clave, clase, fecha, sentido in (
            ("agosto", "oficio", datetime.date(2026, 8, 10), "recibido"),
            ("septiembre", "comunicado", datetime.date(2026, 9, 10), "recibido"),
            ("octubre", "oficio", datetime.date(2026, 10, 10), "recibido"),
        ):
            self.creados[clave] = crear_documento(
                usuario=self.user, direccion=self.direccion, sentido=sentido, clase=clase,
                contraparte="X", asunto=f"Requerimiento de {clave}", fecha=fecha,
            )

    def buscar(self, **extra):
        return self.client.get(reverse("seguimientos_oficios:busqueda"), {"q": "requerimiento", **extra})

    def asuntos(self, respuesta):
        return {r["documento"].asunto.split()[-1] for r in respuesta.context["resultados"]}

    def test_filtra_por_clase(self):
        self.assertEqual(self.asuntos(self.buscar(clase="comunicado")), {"septiembre"})
        self.assertEqual(self.asuntos(self.buscar(clase="oficio")), {"agosto", "octubre"})

    def test_filtra_por_rango_de_fechas(self):
        self.assertEqual(self.asuntos(self.buscar(desde="2026-09-01", hasta="2026-09-30")), {"septiembre"})
        self.assertEqual(self.asuntos(self.buscar(desde="2026-09-15")), {"octubre"})
        self.assertEqual(self.asuntos(self.buscar(hasta="2026-08-31")), {"agosto"})

    def test_filtros_combinados_y_con_el_ambito(self):
        self.assertEqual(self.asuntos(self.buscar(clase="oficio", desde="2026-09-01")), {"octubre"})
        self.assertEqual(self.asuntos(self.buscar(clase="oficio", sentido="enviado")), set())
        self.assertEqual(self.asuntos(self.buscar(direccion=str(self.direccion.pk), clase="comunicado")), {"septiembre"})

    def test_panel_abierto_solo_con_filtros_y_limpiar_conserva_texto_y_ambito(self):
        sin = self.buscar()
        self.assertFalse(sin.context["filtros_activos"])
        con = self.buscar(clase="oficio", sentido="recibido")
        self.assertTrue(con.context["filtros_activos"])
        self.assertContains(con, "q=requerimiento&amp;sentido=recibido")
        self.assertEqual(con.context["query_limpiar"], "q=requerimiento&sentido=recibido")

    def test_los_botones_de_ambito_conservan_los_filtros(self):
        respuesta = self.buscar(clase="oficio", desde="2026-09-01")
        enviados = next(a for a in respuesta.context["ambitos"] if a["clave"] == "enviado")
        self.assertIn("clase=oficio", enviados["query"])
        self.assertIn("desde=2026-09-01", enviados["query"])
        self.assertIn("sentido=enviado", enviados["query"])

    def test_paginacion_conserva_los_filtros(self):
        for n in range(16):
            crear_documento(
                usuario=self.user, direccion=self.direccion, sentido="recibido", clase="comunicado",
                contraparte="X", asunto=f"Requerimiento masivo {n}", fecha=datetime.date(2026, 9, 20),
            )
        respuesta = self.buscar(clase="comunicado")
        self.assertContains(respuesta, "clase=comunicado")
        self.assertContains(respuesta, "pagina=2")

    def test_fecha_invalida_no_rompe_y_conserva_el_texto(self):
        respuesta = self.buscar(desde="no-es-fecha", clase="oficio")
        self.assertEqual(respuesta.status_code, 200)
        self.assertGreaterEqual(len(self.asuntos(respuesta)), 3)
