import datetime
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import override_settings

from satelites.seguimientos_oficios import bandeja
from satelites.seguimientos_oficios.models import Adjunto, ConsecutivoFolio, Documento, Nomenclatura
from satelites.seguimientos_oficios.services import crear_documento

from .base import PDF, BaseAdjuntos


class ImportacionTests(BaseAdjuntos):
    def setUp(self):
        super().setUp()
        self._raiz = tempfile.TemporaryDirectory()
        self.addCleanup(self._raiz.cleanup)
        self.raiz = Path(self._raiz.name).resolve()
        override = override_settings(OFICIOS_BANDEJA_RAIZ=str(self.raiz))
        override.enable()
        self.addCleanup(override.disable)
        self.carpeta = self.raiz / "historico"
        self.carpeta.mkdir()

    def pdf(self, nombre, extra=b""):
        (self.carpeta / nombre).write_bytes(PDF + extra)

    def correr(self, *argumentos):
        salida = StringIO()
        call_command("oficios_importar_historico", "--direccion", "innovacion", "--carpeta", "historico",
                     *argumentos, stdout=salida)
        return salida.getvalue()

    def test_simulacion_no_escribe(self):
        self.pdf("2025-03-10 Oficio de prueba.pdf")
        salida = self.correr("--sentido", "recibido")
        self.assertIn("Se importarían (simulación): 1", salida)
        self.assertEqual(Documento.objects.count(), 0)

    def test_recibidos_sin_csv_usan_nombre_y_fecha_del_nombre(self):
        self.pdf("2025-03-10 Solicitud de equipo.pdf")
        self.correr("--sentido", "recibido", "--aplicar")
        documento = Documento.objects.get()
        self.assertEqual((documento.estado, documento.fecha, documento.director_nombre), ("registrado", datetime.date(2025, 3, 10), ""))
        self.assertIn("Solicitud de equipo", documento.asunto)
        self.assertEqual(documento.adjuntos.get().rol, "original")
        self.assertEqual(documento.adjuntos.get().ocr.estado, "pendiente")
        self.assertEqual(documento.historial.first().usuario_nombre, "Importación histórica")

    def test_enviados_toman_folio_del_nombre_y_suben_el_contador(self):
        self.pdf("IN-045-2025 Dictamen de alta.pdf")
        self.pdf("IN-002-2025 Otro.pdf", b"x")
        self.correr("--sentido", "enviado", "--clase", "oficio", "--aplicar")
        folios = set(Documento.objects.values_list("folio", flat=True))
        self.assertEqual(folios, {"IN-045/2025", "IN-002/2025"})
        self.assertEqual(Documento.objects.get(folio="IN-045/2025").estado, "concluido")
        adjunto = Documento.objects.get(folio="IN-045/2025").adjuntos.get()
        self.assertEqual((adjunto.rol, adjunto.ocr.estado), ("firmado", "pendiente"))
        self.assertEqual(ConsecutivoFolio.objects.get(anio=2025).ultimo, 45)
        siguiente = crear_documento(
            usuario=None, direccion=self.direccion, sentido="enviado", clase="oficio",
            contraparte="X", asunto="Nuevo", fecha=datetime.date(2025, 12, 1),
        )
        self.assertEqual(siguiente.folio, "IN-046/2025")

    def test_csv_define_metadatos_y_el_director_no_es_el_actual(self):
        self.pdf("a.pdf")
        (self.raiz / "manifiesto.csv").write_text(
            "archivo,sentido,clase,fecha,folio,contraparte,asunto,director\n"
            "a.pdf,enviado,oficio,15/01/2025,IN-010/2025,Tesorería,Alta de equipo,Juan Anterior\n"
            "no-esta.pdf,recibido,,,,,,\n", encoding="utf-8")
        salida = self.correr("--csv", str(self.raiz / "manifiesto.csv"), "--aplicar")
        documento = Documento.objects.get()
        self.assertEqual((documento.director_nombre, documento.contraparte, documento.fecha), ("Juan Anterior", "Tesorería", datetime.date(2025, 1, 15)))
        self.assertIn("no-esta.pdf: No está en la carpeta.", salida)

    def test_es_idempotente_y_detecta_duplicados(self):
        self.pdf("2025-01-01 Uno.pdf")
        self.correr("--sentido", "recibido", "--aplicar")
        salida = self.correr("--sentido", "recibido", "--aplicar")
        self.assertIn("Ya existentes (omitidos): 1", salida)
        self.assertEqual((Documento.objects.count(), Adjunto.objects.count()), (1, 1))

    def test_errores_se_reportan_sin_detener_el_resto(self):
        self.pdf("sin-folio.pdf")
        self.pdf("bueno.pdf", b"y")
        (self.carpeta / "roto.pdf").write_bytes(b"no soy pdf")
        salida = self.correr("--sentido", "enviado", "--aplicar")
        self.assertIn("Con error: 3", salida)
        self.assertEqual(Documento.objects.count(), 0)
        self.assertIn("roto.pdf: No es un PDF válido.", salida)

    def test_folio_repetido_no_rompe_y_no_deja_datos_a_medias(self):
        self.pdf("IN-005-2025 A.pdf")
        self.pdf("IN-005-2025 B.pdf", b"z")
        salida = self.correr("--sentido", "enviado", "--aplicar")
        self.assertIn("Folio repetido", salida)
        self.assertEqual((Documento.objects.count(), Adjunto.objects.count()), (1, 1))

    def test_direccion_o_carpeta_inexistente(self):
        with self.assertRaises(CommandError):
            call_command("oficios_importar_historico", "--direccion", "nada", "--carpeta", "historico")
        with self.assertRaises(CommandError):
            call_command("oficios_importar_historico", "--direccion", "innovacion", "--carpeta", "../fuera")

    def test_interpretar_plantilla(self):
        nomenclatura = Nomenclatura.objects.get(direccion=self.direccion, clase="oficio")
        self.assertEqual(nomenclatura.interpretar("IN-045/2025"), (45, 2025))
        self.assertIsNone(nomenclatura.interpretar("XX-045/2025"))
        self.assertEqual(nomenclatura.interpretar("hola IN-7/2024 adiós", buscar=True), (7, 2024))
