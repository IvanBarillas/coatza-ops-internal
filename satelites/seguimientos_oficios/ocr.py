import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings


class OcrNoDisponible(Exception):
    pass


class OcrFallido(Exception):
    pass


MARCA_PAGINAS_OMITIDAS = re.compile(r"\[OCR skipped on page")


def _ejecutar(comando, idioma, limite, ruta_pdf, modo, salida, texto):
    for archivo in (salida, texto):
        archivo.unlink(missing_ok=True)
    try:
        proceso = subprocess.run(
            [comando, "--language", idioma, modo, "--sidecar", str(texto),
             "--output-type", "pdf", str(ruta_pdf), str(salida)],
            capture_output=True, text=True, timeout=limite, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise OcrFallido(f"El OCR excedió {limite} s.") from error
    if proceso.returncode != 0:
        raise OcrFallido((proceso.stderr or proceso.stdout or "OCR falló").strip()[-2000:])
    return texto.read_text(encoding="utf-8", errors="replace") if texto.exists() else ""


def extraer_texto(ruta_pdf, ruta_salida=None):
    """Extrae el texto con OCRmyPDF (Tesseract). El PDF original no se modifica. Si se indica `ruta_salida`,
    ahí queda una copia con capa de texto, pensada solo para el visor (resaltado de palabras).

    Se usa `--skip-text`: conserva las imágenes tal cual, así que la copia pesa casi lo mismo que el original.
    Si alguna página ya traía texto digital, OCRmyPDF la omite y su texto no llega al sidecar; en ese caso (poco
    común) se rehace con `--force-ocr`, que sí lo obtiene aunque la copia sea más pesada."""
    comando = getattr(settings, "OFICIOS_OCR_COMANDO", "ocrmypdf")
    if shutil.which(comando) is None:
        raise OcrNoDisponible(f"No se encontró '{comando}'. Instale ocrmypdf y tesseract con el idioma español.")
    idioma = getattr(settings, "OFICIOS_OCR_IDIOMA", "spa")
    limite = getattr(settings, "OFICIOS_OCR_TIMEOUT", 900)
    with tempfile.TemporaryDirectory() as tmp:
        salida, texto = Path(tmp) / "salida.pdf", Path(tmp) / "texto.txt"
        contenido = _ejecutar(comando, idioma, limite, ruta_pdf, "--skip-text", salida, texto)
        if MARCA_PAGINAS_OMITIDAS.search(contenido):
            contenido = _ejecutar(comando, idioma, limite, ruta_pdf, "--force-ocr", salida, texto)
        if ruta_salida and salida.exists():
            Path(ruta_salida).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(salida), str(ruta_salida))
        return contenido
