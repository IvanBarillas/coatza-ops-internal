import importlib
import tempfile
from pathlib import Path
from unittest import mock

from django.apps import apps as django_apps
from django.core.files.base import ContentFile
from django.test import override_settings

from satelites.seguimientos_oficios import ocr, tasks
from satelites.seguimientos_oficios.models import AdjuntoOCR
from satelites.seguimientos_oficios.services import adjuntar_pdf
from satelites.seguimientos_oficios.storage import almacen, ruta_copia_ocr

from .base import BaseAdjuntos, pdf


class CopiasOcrTests(BaseAdjuntos):
    def test_la_ruta_de_la_copia_va_en_la_carpeta_ocr_con_el_mismo_nombre(self):
        self.assertEqual(
            ruta_copia_ocr("2026/innovacion/recibidos/IN-001__original__abc.pdf"),
            "2026/innovacion/recibidos/ocr/IN-001__original__abc.pdf",
        )
        self.assertEqual(ruta_copia_ocr("a.pdf"), "ocr/a.pdf")

    def test_la_tarea_guarda_la_copia_en_ocr_y_deja_limpia_la_carpeta_de_originales(self):
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            adjunto, _ = adjuntar_pdf(self.documento("recibido"), usuario=self.user, archivo=pdf())

        def motor(ruta, salida=None):
            Path(salida).parent.mkdir(parents=True, exist_ok=True)
            Path(salida).write_bytes(b"%PDF copia")
            return "texto"

        with mock.patch.object(ocr, "extraer_texto", side_effect=motor):
            tasks.procesar_ocr(adjunto.pk)
        adjunto.ocr.refresh_from_db()
        self.assertRegex(adjunto.ocr.ruta_buscable, r"^2026/innovacion/recibidos/ocr/sin-folio__original__[0-9a-f]{12}\.pdf$")
        carpeta = Path(almacen().path(adjunto.ruta)).parent
        self.assertEqual([p.name for p in carpeta.glob("*.pdf")], [Path(adjunto.ruta).name])
        self.assertEqual(len(list((carpeta / "ocr").glob("*.pdf"))), 1)

    def test_la_migracion_mueve_las_copias_viejas_a_la_carpeta_ocr(self):
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            con_copia, _ = adjuntar_pdf(self.documento("recibido"), usuario=self.user, archivo=pdf("a.pdf", b"%PDF-1.4 a"))
            sin_archivo, _ = adjuntar_pdf(self.documento("recibido"), usuario=self.user, archivo=pdf("b.pdf", b"%PDF-1.4 b"))
        vieja = con_copia.ruta.removesuffix(".pdf") + "__buscable.pdf"
        almacen().save(vieja, ContentFile(b"%PDF copia vieja"))
        AdjuntoOCR.objects.filter(adjunto=con_copia).update(estado="listo", ruta_buscable=vieja)
        AdjuntoOCR.objects.filter(adjunto=sin_archivo).update(estado="listo", ruta_buscable="2026/no/existe__buscable.pdf")
        migracion = importlib.import_module("satelites.seguimientos_oficios.migrations.0020_copias_en_carpeta_ocr")
        migracion.mover_copias(django_apps, None)
        nueva = AdjuntoOCR.objects.get(adjunto=con_copia).ruta_buscable
        self.assertEqual(nueva, ruta_copia_ocr(con_copia.ruta))
        self.assertEqual(Path(almacen().path(nueva)).read_bytes(), b"%PDF copia vieja")
        self.assertFalse(almacen().exists(vieja))
        self.assertEqual(AdjuntoOCR.objects.get(adjunto=sin_archivo).ruta_buscable, "")
        migracion.mover_copias(django_apps, None)  # idempotente
        self.assertEqual(AdjuntoOCR.objects.get(adjunto=con_copia).ruta_buscable, nueva)
