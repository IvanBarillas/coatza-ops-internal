from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


def almacen():
    raiz = getattr(settings, "OFICIOS_ARCHIVOS_ROOT", None) or Path(settings.MEDIA_ROOT) / "oficios"
    return FileSystemStorage(location=str(raiz), base_url=None)


def ruta_por_contenido(sha256, fecha):
    return f"{fecha:%Y/%m}/{sha256[:2]}/{sha256}.pdf"
