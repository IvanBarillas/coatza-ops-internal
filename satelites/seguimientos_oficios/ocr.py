import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings


class OcrNoDisponible(Exception):
    pass


class OcrFallido(Exception):
    pass


def extraer_texto(ruta_pdf):
    """Extrae el texto con OCRmyPDF (Tesseract). El PDF original no se modifica:
    la salida con capa de texto se descarta y solo se conserva el texto (sidecar)."""
    comando = getattr(settings, "OFICIOS_OCR_COMANDO", "ocrmypdf")
    if shutil.which(comando) is None:
        raise OcrNoDisponible(f"No se encontró '{comando}'. Instale ocrmypdf y tesseract con el idioma español.")
    idioma = getattr(settings, "OFICIOS_OCR_IDIOMA", "spa")
    limite = getattr(settings, "OFICIOS_OCR_TIMEOUT", 900)
    with tempfile.TemporaryDirectory() as tmp:
        salida, texto = Path(tmp) / "salida.pdf", Path(tmp) / "texto.txt"
        try:
            proceso = subprocess.run(
                [comando, "--language", idioma, "--skip-text", "--sidecar", str(texto),
                 "--output-type", "pdf", str(ruta_pdf), str(salida)],
                capture_output=True, text=True, timeout=limite, check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise OcrFallido(f"El OCR excedió {limite} s.") from error
        if proceso.returncode != 0:
            raise OcrFallido((proceso.stderr or proceso.stdout or "OCR falló").strip()[-2000:])
        return texto.read_text(encoding="utf-8", errors="replace") if texto.exists() else ""
