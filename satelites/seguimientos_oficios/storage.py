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
