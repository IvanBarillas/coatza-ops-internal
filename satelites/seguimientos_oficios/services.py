import hashlib

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .integracion import director_de_dependencia, encolar_tarea, nombre_de_usuario
from .models import Adjunto, AdjuntoOCR, ConsecutivoFolio, Documento, HistorialDocumento, Nomenclatura
from .storage import almacen, ruta_por_contenido
from .tasks import TAREA_OCR, TIMEOUT_TAREA

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


TAMANO_MAXIMO = 25 * 1024 * 1024


def _leer_pdf(archivo):
    if archivo is None:
        raise ValidationError("Seleccione un archivo PDF.")
    if archivo.size > TAMANO_MAXIMO:
        raise ValidationError("El archivo excede el tamaño máximo de 25 MB.")
    contenido = archivo.read()
    if not contenido.startswith(b"%PDF-"):
        raise ValidationError("El archivo no es un PDF válido.")
    return contenido


@transaction.atomic
def adjuntar_pdf(documento, *, usuario, archivo):
    """Agrega el PDF con el rol que corresponde al sentido. Devuelve (adjunto, duplicado)."""
    documento = Documento.objects.select_for_update().get(pk=documento.pk)
    if documento.sentido == Documento.Sentido.RECIBIDO:
        rol, permitidos = Adjunto.Rol.ORIGINAL, {Documento.Estado.REGISTRADO}
        mensaje = "Solo se adjunta el original a un documento recibido en estado Registrado."
    else:
        rol = Adjunto.Rol.EVIDENCIA
        permitidos = {Documento.Estado.ENTREGADO, Documento.Estado.CONCLUIDO}
        mensaje = "La evidencia se adjunta cuando el documento ya fue entregado."
    if documento.estado not in permitidos:
        raise ValidationError(mensaje)
    contenido = _leer_pdf(archivo)
    sha256 = hashlib.sha256(contenido).hexdigest()
    duplicado = Adjunto.objects.filter(sha256=sha256).exclude(documento=documento).select_related("documento").first()
    ruta = ruta_por_contenido(sha256, timezone.now())
    almacen_ = almacen()
    existente = Adjunto.objects.filter(sha256=sha256).values_list("ruta", flat=True).first()
    if existente:
        ruta = existente
    elif not almacen_.exists(ruta):
        almacen_.save(ruta, ContentFile(contenido))
    adjunto = Adjunto.objects.create(
        documento=documento, rol=rol, ruta=ruta, nombre_original=archivo.name[:255],
        sha256=sha256, tamano=len(contenido), subido_por=usuario,
        subido_por_nombre=nombre_de_usuario(usuario),
    )
    _preparar_ocr(adjunto)
    datos = {"adjunto": archivo.name, "rol": rol, "sha256": sha256, "tamano": len(contenido)}
    if duplicado:
        datos["duplicado_de"] = duplicado.documento.folio or str(duplicado.documento_id)
    if rol == Adjunto.Rol.EVIDENCIA and documento.estado == Documento.Estado.ENTREGADO:
        documento.estado = Documento.Estado.CONCLUIDO
        documento.save()
        datos.update(estado_anterior=Documento.Estado.ENTREGADO, estado_nuevo=documento.estado)
    _historial(documento, HistorialDocumento.Accion.ADJUNTADO, usuario, datos)
    return adjunto, duplicado


def _preparar_ocr(adjunto):
    previo = (
        AdjuntoOCR.objects.filter(adjunto__sha256=adjunto.sha256, estado=AdjuntoOCR.Estado.LISTO)
        .exclude(adjunto=adjunto).first()
    )
    if previo:
        AdjuntoOCR.objects.create(
            adjunto=adjunto, estado=AdjuntoOCR.Estado.LISTO, texto=previo.texto,
            terminado_en=timezone.now(),
        )
        return
    AdjuntoOCR.objects.create(adjunto=adjunto)
    transaction.on_commit(lambda: encolar_tarea(TAREA_OCR, str(adjunto.pk), timeout=TIMEOUT_TAREA))
