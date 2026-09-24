from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .integracion import director_de_dependencia, nombre_de_usuario
from .models import ConsecutivoFolio, Documento, Nomenclatura, HistorialDocumento

MOTIVO_MINIMO = 10


def _siguiente_folio(direccion, clase, anio):
    nomenclatura = Nomenclatura.objects.filter(
        direccion=direccion, clase=clase, is_active=True, is_deleted=False
    ).first()
    if nomenclatura is None:
        raise ValidationError("No hay nomenclatura configurada para esta dirección y clase de documento.")
    ConsecutivoFolio.objects.get_or_create(nomenclatura=nomenclatura, anio=anio)
    consecutivo = ConsecutivoFolio.objects.select_for_update().get(nomenclatura=nomenclatura, anio=anio)
    consecutivo.ultimo += 1
    consecutivo.save(update_fields=["ultimo"])
    return consecutivo.ultimo, nomenclatura.formatear(consecutivo.ultimo, anio)


@transaction.atomic
def crear_documento(*, usuario, direccion, sentido, clase, contraparte, asunto, fecha,
                    folio="", director_nombre=""):
    anio = consecutivo = None
    if sentido == Documento.Sentido.ENVIADO:
        consecutivo, folio = _siguiente_folio(direccion, clase, fecha.year)
        anio = fecha.year
    documento = Documento.objects.create(
        sentido=sentido, clase=clase, direccion=direccion, direccion_nombre=direccion.nombre,
        contraparte=contraparte, asunto=asunto, fecha=fecha, folio=folio,
        anio=anio, consecutivo=consecutivo, creado_por=usuario,
        estado=(Documento.Estado.GENERADO if sentido == Documento.Sentido.ENVIADO else Documento.Estado.REGISTRADO),
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


def _historial(documento, accion, usuario, datos):
    HistorialDocumento.objects.create(
        documento=documento, accion=accion, usuario=usuario,
        usuario_nombre=nombre_de_usuario(usuario), datos=datos,
    )


@transaction.atomic
def marcar_entregado(documento, *, usuario, fecha_entrega, receptor):
    documento = Documento.objects.select_for_update().get(pk=documento.pk)
    if documento.sentido != Documento.Sentido.ENVIADO or documento.estado != Documento.Estado.GENERADO:
        raise ValidationError("Solo un documento enviado en estado Generado puede marcarse como entregado.")
    if not (receptor or "").strip():
        raise ValidationError("Indique quién recibió la entrega.")
    documento.estado = Documento.Estado.ENTREGADO
    documento.fecha_entrega = fecha_entrega
    documento.receptor_entrega = receptor.strip()
    documento.save()
    _historial(documento, HistorialDocumento.Accion.EDITADO, usuario, {
        "estado_anterior": Documento.Estado.GENERADO, "estado_nuevo": documento.estado,
        "fecha_entrega": fecha_entrega.isoformat(), "receptor": documento.receptor_entrega,
    })
    return documento


@transaction.atomic
def cancelar_documento(documento, *, usuario, motivo, puede_cancelar_concluido=False):
    documento = Documento.objects.select_for_update().get(pk=documento.pk)
    motivo = (motivo or "").strip()
    if len(motivo) < MOTIVO_MINIMO:
        raise ValidationError(f"El motivo debe tener al menos {MOTIVO_MINIMO} caracteres.")
    if documento.estado == Documento.Estado.CANCELADO:
        raise ValidationError("El documento ya está cancelado.")
    if documento.estado == Documento.Estado.CONCLUIDO and not puede_cancelar_concluido:
        raise ValidationError("Cancelar un documento concluido requiere un permiso especial.")
    anterior = documento.estado
    documento.estado = Documento.Estado.CANCELADO
    documento.motivo_cancelacion = motivo
    documento.save()
    _historial(documento, HistorialDocumento.Accion.ELIMINADO, usuario, {
        "estado_anterior": anterior, "estado_nuevo": documento.estado, "motivo": motivo,
        "cancelado_en": timezone.now().isoformat(),
    })
    return documento
