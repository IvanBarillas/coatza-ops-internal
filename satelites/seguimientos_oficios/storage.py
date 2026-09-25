import re
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage

from .integracion import valor_entorno


def almacen():
    raiz = valor_entorno("OFICIOS_ARCHIVOS_ROOT") or Path(settings.MEDIA_ROOT) / "oficios"
    return FileSystemStorage(location=str(raiz), base_url=None)


def ruta_del_adjunto(documento, rol, sha256):
    """AAAA/direccion/recibidos|enviados/FOLIO__rol__hash.pdf; legible al navegar el almacén."""
    folio = re.sub(r"[^A-Za-z0-9._-]+", "-", documento.folio or "").strip("-") or "sin-folio"
    carpeta = "recibidos" if documento.sentido == "recibido" else "enviados"
    return f"{documento.fecha.year}/{documento.direccion.slug}/{carpeta}/{folio}__{rol}__{sha256[:12]}.pdf"


def ruta_copia_ocr(ruta_original):
    """Copia con texto del visor: misma ruta y nombre que el original pero dentro de una carpeta `ocr/`, para que
    los originales se puedan entregar (p. ej. en una auditoría) sin arrastrar las copias."""
    carpeta, _, nombre = ruta_original.rpartition("/")
    return f"{carpeta}/ocr/{nombre}" if carpeta else f"ocr/{nombre}"
