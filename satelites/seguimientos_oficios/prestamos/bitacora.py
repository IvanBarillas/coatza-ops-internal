from ..integracion import nombre_de_usuario
from ..models import HistorialBien


def registrar(bien, accion, usuario, datos, usuario_nombre=None):
    return HistorialBien.objects.create(
        bien=bien, accion=accion, usuario=usuario, datos=datos,
        usuario_nombre=nombre_de_usuario(usuario) if usuario_nombre is None else usuario_nombre,
    )
