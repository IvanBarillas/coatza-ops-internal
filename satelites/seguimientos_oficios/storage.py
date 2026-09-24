from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage

from .integracion import valor_entorno


def almacen():
    raiz = valor_entorno("OFICIOS_ARCHIVOS_ROOT") or Path(settings.MEDIA_ROOT) / "oficios"
    return FileSystemStorage(location=str(raiz), base_url=None)


def ruta_por_contenido(sha256, fecha):
    return f"{fecha:%Y/%m}/{sha256[:2]}/{sha256}.pdf"
