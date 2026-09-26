from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage

from .integracion import valor_entorno


def almacen():
    raiz = valor_entorno("TEL_ARCHIVOS_ROOT") or Path(settings.MEDIA_ROOT) / "telefonia"
    return FileSystemStorage(location=str(raiz), base_url=None)


def ruta_de_evidencia(reporte, tipo, sha256, extension):
    """AAAA/FOLIO/tipo__hash.ext; legible al navegar el almacén."""
    import re

    folio = re.sub(r"[^A-Za-z0-9._-]+", "-", reporte.folio or "").strip("-") or "sin-folio"
    return f"{reporte.levantado.year}/{folio}/{tipo}__{sha256[:12]}.{extension}"
