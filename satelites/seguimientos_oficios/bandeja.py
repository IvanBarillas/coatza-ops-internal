import os
from datetime import datetime
from pathlib import Path

from .integracion import valor_entorno

LIMITE_LISTADO = 200


class BandejaError(Exception):
    pass


def raiz():
    valor = valor_entorno("OFICIOS_BANDEJA_RAIZ")
    return Path(valor).resolve() if valor else None


def resolver(ruta_relativa, *, debe_existir=True):
    """Carpeta absoluta dentro de la carpeta base de importación; rechaza '..' y enlaces simbólicos que salgan de ella."""
    base = raiz()
    if base is None:
        raise BandejaError("Falta definir OFICIOS_BANDEJA_RAIZ, la carpeta base desde la que se importan PDF.")
    relativa = (ruta_relativa or "").strip().strip("/")
    if not relativa:
        raise BandejaError("Indique la carpeta.")
    destino = (base / relativa).resolve()
    if destino != base and not destino.is_relative_to(base):
        raise BandejaError("La carpeta debe estar dentro de OFICIOS_BANDEJA_RAIZ.")
    if debe_existir and not destino.is_dir():
        raise BandejaError("La carpeta no existe o no es accesible desde el servidor.")
    return destino


def listar_pdfs(carpeta):
    archivos = []
    try:
        with os.scandir(carpeta) as entradas:
            for entrada in entradas:
                if (entrada.name.startswith(".") or not entrada.name.lower().endswith(".pdf")
                        or not entrada.is_file(follow_symlinks=False)):
                    continue
                datos = entrada.stat(follow_symlinks=False)
                archivos.append({
                    "nombre": entrada.name, "tamano": datos.st_size,
                    "modificado": datetime.fromtimestamp(datos.st_mtime),
                })
    except OSError as error:
        raise BandejaError(f"No se pudo leer la carpeta: {error.strerror or error}") from error
    archivos.sort(key=lambda a: a["modificado"], reverse=True)
    return archivos[:LIMITE_LISTADO]


def _archivo_seguro(carpeta, nombre):
    if not nombre or nombre != Path(nombre).name or nombre.startswith(".") or not nombre.lower().endswith(".pdf"):
        raise BandejaError("Nombre de archivo no válido.")
    ruta = carpeta / nombre
    if ruta.is_symlink() or not ruta.is_file():
        raise BandejaError("El archivo ya no está en la bandeja.")
    return ruta


def leer(carpeta, nombre, *, tamano_maximo):
    ruta = _archivo_seguro(carpeta, nombre)
    if ruta.stat().st_size > tamano_maximo:
        raise BandejaError("El archivo excede el tamaño máximo permitido.")
    try:
        return ruta.read_bytes()
    except OSError as error:
        raise BandejaError(f"No se pudo leer el archivo: {error.strerror or error}") from error
