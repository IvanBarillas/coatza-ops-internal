from django.core.exceptions import ValidationError
from django.db import transaction

from .integracion import director_de_dependencia, nombre_de_usuario
from .models import ConsecutivoFolio, Documento, HistorialDocumento


def _siguiente_folio(direccion, anio):
    if not direccion.prefijo:
        raise ValidationError("La dirección no tiene prefijo de folio configurado.")
    ConsecutivoFolio.objects.get_or_create(direccion=direccion, anio=anio)
    consecutivo = ConsecutivoFolio.objects.select_for_update().get(direccion=direccion, anio=anio)
    consecutivo.ultimo += 1
    consecutivo.save(update_fields=["ultimo"])
    return consecutivo.ultimo, f"{direccion.prefijo}-{consecutivo.ultimo:03d}/{anio}"


@transaction.atomic
def crear_documento(*, usuario, direccion, sentido, clase, contraparte, asunto, fecha,
                    folio="", director_nombre=""):
    anio = consecutivo = None
    if sentido == Documento.Sentido.ENVIADO:
        consecutivo, folio = _siguiente_folio(direccion, fecha.year)
        anio = fecha.year
    documento = Documento.objects.create(
        sentido=sentido, clase=clase, direccion=direccion, direccion_nombre=direccion.nombre,
        contraparte=contraparte, asunto=asunto, fecha=fecha, folio=folio,
        anio=anio, consecutivo=consecutivo, creado_por=usuario,
        director_nombre=director_nombre or director_de_dependencia(direccion.dependencia_uuid),
    )
    HistorialDocumento.objects.create(
        documento=documento, accion=HistorialDocumento.Accion.CREADO,
        usuario=usuario, usuario_nombre=nombre_de_usuario(usuario),
        datos={
            "sentido": sentido, "clase": clase, "folio": documento.folio,
            "direccion": documento.direccion_nombre, "director": documento.director_nombre,
            "contraparte": contraparte, "asunto": asunto, "fecha": fecha.isoformat(),
        },
    )
    return documento
