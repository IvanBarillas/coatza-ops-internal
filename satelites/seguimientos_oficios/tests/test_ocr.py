import stat
import tempfile
from pathlib import Path
from unittest import mock

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import override_settings

from satelites.seguimientos_oficios import ocr, tasks
from satelites.seguimientos_oficios.models import AdjuntoOCR
from satelites.seguimientos_oficios.services import adjuntar_pdf
from satelites.seguimientos_oficios.storage import almacen, ruta_copia_ocr

from .base import BaseAdjuntos, pdf

FALSO_OCRMYPDF = """#!/bin/sh
# Simula ocrmypdf: escribe la copia (último argumento) y el sidecar; registra cada invocación.
for ultimo; do :; done
modo=""
while [ "$#" -gt 0 ]; do
  case "$1" in --force-ocr|--skip-text) modo="$1" ;; esac
  [ "$1" = "--sidecar" ] && { shift; sidecar="$1"; }
  shift
done
echo "$modo" >> "$(dirname "$0")/invocaciones.txt"
echo "pdf con capa de texto ($modo)" > "$ultimo"
if [ "$modo" = "--skip-text" ] && [ -f "$(dirname "$0")/digital" ]; then
  printf '[OCR skipped on page(s) 1]\\f' > "$sidecar"
else
  echo "Texto reconocido del oficio" > "$sidecar"
fi
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
            self.assertEqual((Path(tmp) / "invocaciones.txt").read_text().split(), ["--skip-text"])


    def test_el_motor_deja_la_copia_con_texto_donde_se_le_pide(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "falso-ocrmypdf"
            script.write_text(FALSO_OCRMYPDF)
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
            destino = Path(tmp) / "carpeta" / "nueva" / "copia.pdf"
            with override_settings(OFICIOS_OCR_COMANDO=str(script)):
                ocr.extraer_texto(Path(tmp) / "entrada.pdf", destino)
            self.assertEqual(destino.read_text().strip(), "pdf con capa de texto (--skip-text)")

    def test_la_tarea_registra_la_copia_solo_si_se_genero(self):
        adjunto = self.adjunto()

        def motor_que_escribe(ruta, salida=None):
            Path(salida).parent.mkdir(parents=True, exist_ok=True)
            Path(salida).write_bytes(b"%PDF copia")
            return "texto"

        with mock.patch.object(ocr, "extraer_texto", side_effect=motor_que_escribe):
            tasks.procesar_ocr(adjunto.pk)
        adjunto.ocr.refresh_from_db()
        self.assertIn("/ocr/", adjunto.ocr.ruta_buscable)
        self.assertTrue(almacen().exists(adjunto.ocr.ruta_buscable))

        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            otro, _ = adjuntar_pdf(self.documento("recibido"), usuario=self.user, archivo=pdf("distinto.pdf", b"%PDF-1.4 distinto"))
        with mock.patch.object(ocr, "extraer_texto", return_value="solo texto"):
            tasks.procesar_ocr(otro.pk)
        otro.ocr.refresh_from_db()
        self.assertEqual(otro.ocr.ruta_buscable, "")

    def test_reprocesar_con_buscables_rehace_lo_ya_procesado_sin_copia(self):
        adjunto = self.adjunto()
        AdjuntoOCR.objects.filter(adjunto=adjunto).update(estado="listo", texto="viejo", ruta_buscable="")

        def motor(ruta, salida=None):
            Path(salida).parent.mkdir(parents=True, exist_ok=True)
            Path(salida).write_bytes(b"%PDF copia")
            return "nuevo"

        with mock.patch.object(ocr, "extraer_texto", side_effect=motor):
            call_command("oficios_reprocesar_ocr", stdout=mock.MagicMock())
            self.assertEqual(AdjuntoOCR.objects.get(adjunto=adjunto).texto, "viejo")
            call_command("oficios_reprocesar_ocr", "--buscables", stdout=mock.MagicMock())
        registro = AdjuntoOCR.objects.get(adjunto=adjunto)
        self.assertEqual((registro.texto, bool(registro.ruta_buscable)), ("nuevo", True))

    def test_un_archivo_igual_reutiliza_tambien_la_copia_con_texto(self):
        primero = self.adjunto()

        def motor(ruta, salida=None):
            Path(salida).parent.mkdir(parents=True, exist_ok=True)
            Path(salida).write_bytes(b"%PDF copia")
            return "texto"

        with mock.patch.object(ocr, "extraer_texto", side_effect=motor):
            tasks.procesar_ocr(primero.pk)
        primero.ocr.refresh_from_db()
        with mock.patch("satelites.seguimientos_oficios.services.encolar_tarea"):
            segundo, _ = adjuntar_pdf(self.documento("recibido"), usuario=self.user, archivo=pdf("copia.pdf"))
        self.assertEqual(segundo.ocr.ruta_buscable, primero.ocr.ruta_buscable)


    def _script(self, tmp, digital=False):
        script = Path(tmp) / "falso-ocrmypdf"
        script.write_text(FALSO_OCRMYPDF)
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        if digital:
            (Path(tmp) / "digital").write_text("1")
        return script

    def test_un_escaneo_se_procesa_una_sola_vez_conservando_las_imagenes(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = self._script(tmp)
            destino = Path(tmp) / "copia.pdf"
            with override_settings(OFICIOS_OCR_COMANDO=str(script)):
                texto = ocr.extraer_texto(Path(tmp) / "entrada.pdf", destino)
            self.assertEqual((Path(tmp) / "invocaciones.txt").read_text().split(), ["--skip-text"])
            self.assertIn("Texto reconocido", texto)
            self.assertIn("--skip-text", destino.read_text())

    def test_si_hay_paginas_con_texto_digital_se_rehace_forzando_el_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = self._script(tmp, digital=True)
            destino = Path(tmp) / "copia.pdf"
            with override_settings(OFICIOS_OCR_COMANDO=str(script)):
                texto = ocr.extraer_texto(Path(tmp) / "entrada.pdf", destino)
            self.assertEqual((Path(tmp) / "invocaciones.txt").read_text().split(), ["--skip-text", "--force-ocr"])
            self.assertNotIn("OCR skipped", texto)
            self.assertIn("--force-ocr", destino.read_text())

    def test_reprocesar_buscables_rehace_las_copias_que_pesan_mas_del_doble(self):
        adjunto = self.adjunto()
        copia = ruta_copia_ocr(adjunto.ruta)
        almacen().save(copia, ContentFile(b"%PDF-1.4 " + b"x" * 5000))
        AdjuntoOCR.objects.filter(adjunto=adjunto).update(estado="listo", texto="viejo", ruta_buscable=copia)
        ligera = almacen().path(copia)

        def motor(ruta, salida=None):
            Path(salida).parent.mkdir(parents=True, exist_ok=True)
            Path(salida).write_bytes(b"%PDF-1.4 ligera")
            return "nuevo"

        with mock.patch.object(ocr, "extraer_texto", side_effect=motor):
            call_command("oficios_reprocesar_ocr", "--buscables", stdout=mock.MagicMock())
        self.assertEqual(AdjuntoOCR.objects.get(adjunto=adjunto).texto, "nuevo")
        self.assertLess(Path(ligera).stat().st_size, 100)
        # una copia razonable ya no se toca
        AdjuntoOCR.objects.filter(adjunto=adjunto).update(texto="estable")
        with mock.patch.object(ocr, "extraer_texto", side_effect=motor):
            call_command("oficios_reprocesar_ocr", "--buscables", stdout=mock.MagicMock())
        self.assertEqual(AdjuntoOCR.objects.get(adjunto=adjunto).texto, "estable")
