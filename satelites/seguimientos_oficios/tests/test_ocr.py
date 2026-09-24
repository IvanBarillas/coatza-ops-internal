import stat
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import override_settings

from satelites.seguimientos_oficios import ocr, tasks
from satelites.seguimientos_oficios.models import AdjuntoOCR
from satelites.seguimientos_oficios.services import adjuntar_pdf

from .base import BaseAdjuntos, pdf

FALSO_OCRMYPDF = """#!/bin/sh
case "$*" in *--force-ocr*) ;; *) echo "falta --force-ocr" >&2; exit 1 ;; esac
while [ "$#" -gt 0 ]; do
  [ "$1" = "--sidecar" ] && { shift; echo "Texto reconocido del oficio" > "$1"; }
  shift
done
"""


class OcrTests(BaseAdjuntos):
    def adjunto(self, sentido="recibido"):
        documento = self.documento(sentido) if sentido == "recibido" else self.entregado()
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            adjunto, _ = adjuntar_pdf(documento, usuario=self.user, archivo=pdf())
        return adjunto

    def test_al_adjuntar_se_encola_el_ocr_tras_el_commit(self):
        documento = self.documento("recibido")
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea") as encolar:
            with self.captureOnCommitCallbacks(execute=True):
                adjunto, _ = adjuntar_pdf(documento, usuario=self.user, archivo=pdf())
        self.assertEqual(adjunto.ocr.estado, "pendiente")
        encolar.assert_called_once_with(tasks.TAREA_OCR, str(adjunto.pk), timeout=tasks.TIMEOUT_TAREA)

    def test_tarea_guarda_el_texto(self):
        adjunto = self.adjunto()
        with mock.patch.object(ocr, "extraer_texto", return_value="folio 123 tesorería"):
            self.assertEqual(tasks.procesar_ocr(adjunto.pk), "listo")
        adjunto.ocr.refresh_from_db()
        self.assertEqual((adjunto.ocr.estado, adjunto.ocr.texto, adjunto.ocr.intentos), ("listo", "folio 123 tesorería", 1))

    def test_fallo_del_motor_deja_error_sin_romper(self):
        adjunto = self.adjunto()
        with mock.patch.object(ocr, "extraer_texto", side_effect=ocr.OcrNoDisponible("falta tesseract")):
            self.assertEqual(tasks.procesar_ocr(adjunto.pk), "error")
        adjunto.ocr.refresh_from_db()
        self.assertIn("falta tesseract", adjunto.ocr.error)

    def test_tarea_reentregada_mientras_procesa_se_omite(self):
        adjunto = self.adjunto()
        AdjuntoOCR.objects.filter(adjunto=adjunto).update(estado="procesando")
        with mock.patch.object(ocr, "extraer_texto") as motor:
            self.assertEqual(tasks.procesar_ocr(adjunto.pk), "omitido")
        motor.assert_not_called()

    def test_reprocesar_reintenta_los_errores(self):
        adjunto = self.adjunto()
        AdjuntoOCR.objects.filter(adjunto=adjunto).update(estado="error", error="x")
        with mock.patch.object(ocr, "extraer_texto", return_value="ok"):
            call_command("oficios_reprocesar_ocr", stdout=mock.MagicMock())
        adjunto.ocr.refresh_from_db()
        self.assertEqual(adjunto.ocr.estado, "listo")

    def test_reprocesar_crea_el_ocr_de_adjuntos_anteriores(self):
        adjunto = self.adjunto()
        AdjuntoOCR.objects.filter(adjunto=adjunto).delete()
        with mock.patch.object(ocr, "extraer_texto", return_value="antiguo"):
            call_command("oficios_reprocesar_ocr", stdout=mock.MagicMock())
        self.assertEqual(AdjuntoOCR.objects.get(adjunto=adjunto).texto, "antiguo")

    def test_mismo_archivo_reutiliza_el_texto_ya_extraido(self):
        primero = self.adjunto()
        with mock.patch.object(ocr, "extraer_texto", return_value="texto único"):
            tasks.procesar_ocr(primero.pk)
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea") as encolar:
            with self.captureOnCommitCallbacks(execute=True):
                segundo, _ = adjuntar_pdf(self.documento("recibido"), usuario=self.user, archivo=pdf("copia.pdf"))
        self.assertEqual((segundo.ocr.estado, segundo.ocr.texto), ("listo", "texto único"))
        encolar.assert_not_called()

    def test_extraer_texto_sin_comando_instalado(self):
        with override_settings(OFICIOS_OCR_COMANDO="ocrmypdf-que-no-existe"):
            with self.assertRaises(ocr.OcrNoDisponible):
                ocr.extraer_texto("/tmp/x.pdf")

    def test_extraer_texto_invoca_el_comando_y_lee_el_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "falso-ocrmypdf"
            script.write_text(FALSO_OCRMYPDF)
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
            with override_settings(OFICIOS_OCR_COMANDO=str(script)):
                self.assertIn("Texto reconocido", ocr.extraer_texto(Path(tmp) / "entrada.pdf"))
