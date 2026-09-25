import hashlib

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .integracion import director_de_dependencia, encolar_tarea, nombre_de_usuario
from .models import Adjunto, AdjuntoOCR, ConsecutivoFolio, Documento, HistorialDocumento, Nomenclatura
from .storage import almacen, ruta_del_adjunto
from .tasks import TAREA_OCR, TIMEOUT_TAREA

MOTIVO_MINIMO = 10


def _validar_gestor(gestor, direccion, sentido):
    if gestor is None:
        return
    if sentido != Documento.Sentido.ENVIADO:
        raise ValidationError("Solo los documentos enviados llevan gestor.")
    if gestor.direccion_id != direccion.pk or not gestor.is_active or gestor.is_deleted:
        raise ValidationError("El gestor no pertenece a la dirección o está inactivo.")


def _folio_capturado(direccion, folio):
    folio = (folio or "").strip()
    if not folio:
        raise ValidationError("Escriba el folio del oficio.")
    if Documento.objects.filter(direccion=direccion, sentido=Documento.Sentido.ENVIADO, folio=folio).exists():
        raise ValidationError(f"Ya existe un oficio enviado con el folio {folio} en esta dirección.")
    return folio


def sincronizar_contador(nomenclatura, anio, consecutivo):
    """Sube el contador hasta el mayor folio conocido, para que el siguiente automático continúe la serie."""
    ConsecutivoFolio.objects.get_or_create(nomenclatura=nomenclatura, anio=anio)
    contador = ConsecutivoFolio.objects.select_for_update().get(nomenclatura=nomenclatura, anio=anio)
    if consecutivo > contador.ultimo:
        contador.ultimo = consecutivo
        contador.save(update_fields=["ultimo"])


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
                    folio="", director_nombre="", gestor=None, contraparte_dependencia_uuid=None):
    _validar_gestor(gestor, direccion, sentido)
    anio = consecutivo = None
    nomenclatura, folio_manual = None, False
    if sentido == Documento.Sentido.ENVIADO and direccion.folio_manual:
        folio, folio_manual = _folio_capturado(direccion, folio), True
        nomenclatura = Nomenclatura.objects.filter(
            direccion=direccion, clase=clase, is_active=True, is_deleted=False
        ).first()
        interpretado = nomenclatura.interpretar(folio) if nomenclatura else None
        if interpretado:
            consecutivo, anio = interpretado[0], interpretado[1] or fecha.year
    elif sentido == Documento.Sentido.ENVIADO:
        consecutivo, folio = _siguiente_folio(direccion, clase, fecha.year)
        anio = fecha.year
    documento = Documento.objects.create(
        sentido=sentido, clase=clase, direccion=direccion, direccion_nombre=direccion.nombre,
        contraparte=contraparte, contraparte_dependencia_uuid=contraparte_dependencia_uuid,
        asunto=asunto, fecha=fecha, folio=folio,
        anio=anio, consecutivo=consecutivo, creado_por=usuario, folio_manual=folio_manual,
        estado=(Documento.Estado.GENERADO if sentido == Documento.Sentido.ENVIADO else Documento.Estado.REGISTRADO),
        director_nombre=director_nombre or director_de_dependencia(direccion.dependencia_uuid),
        gestor=gestor,
    )
    if folio_manual and consecutivo:
        sincronizar_contador(nomenclatura, anio, consecutivo)
    HistorialDocumento.objects.create(
        documento=documento, accion=HistorialDocumento.Accion.CREADO,
        usuario=usuario, usuario_nombre=nombre_de_usuario(usuario),
        datos={
            "sentido": sentido, "clase": clase, "folio": documento.folio,
            "direccion": documento.direccion_nombre, "director": documento.director_nombre,
            "contraparte": contraparte, "asunto": asunto, "fecha": fecha.isoformat(),
            "gestor": gestor.nombre if gestor else None,
        },
    )
    return documento


def _historial(documento, accion, usuario, datos, usuario_nombre=None):
    HistorialDocumento.objects.create(
        documento=documento, accion=accion, usuario=usuario, datos=datos,
        usuario_nombre=nombre_de_usuario(usuario) if usuario_nombre is None else usuario_nombre,
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


def roles_permitidos(documento):
    """Tipos de archivo que se pueden adjuntar hoy al documento, el más habitual primero."""
    Estado, Rol = Documento.Estado, Adjunto.Rol
    if documento.estado == Estado.CANCELADO:
        return []
    if documento.sentido == Documento.Sentido.RECIBIDO:
        return [Rol.ORIGINAL] if documento.estado == Estado.REGISTRADO else []
    if documento.estado == Estado.GENERADO:
        return [Rol.FIRMADO]
    return [Rol.EVIDENCIA, Rol.FIRMADO]


def _elegir_rol(documento, rol):
    permitidos = roles_permitidos(documento)
    if not permitidos:
        raise ValidationError("A este documento ya no se le pueden adjuntar archivos.")
    rol = rol or permitidos[0]
    if rol not in permitidos:
        etiquetas = ", ".join(Adjunto.Rol(r).label for r in permitidos)
        raise ValidationError(f"En este estado solo se puede adjuntar: {etiquetas}.")
    return rol


@transaction.atomic
def adjuntar_pdf(documento, *, usuario, archivo, origen="subida", rol=None):
    """Agrega el PDF con el tipo indicado (o el habitual del estado). Devuelve (adjunto, duplicado)."""
    documento = Documento.objects.select_for_update().get(pk=documento.pk)
    rol = _elegir_rol(documento, rol)
    contenido = _leer_pdf(archivo)
    return registrar_adjunto(
        documento, rol=rol, contenido=contenido, nombre=archivo.name, usuario=usuario,
        origen=origen, concluir=True,
    )


def registrar_adjunto(documento, *, rol, contenido, nombre, usuario, origen, concluir=False, encolar=True,
                     usuario_nombre=None):
    """Guarda el PDF y su registro; no valida el estado (lo hacen quienes lo llaman)."""
    sha256 = hashlib.sha256(contenido).hexdigest()
    duplicado = Adjunto.objects.filter(sha256=sha256, eliminado=False).exclude(documento=documento).select_related("documento").first()
    ruta = ruta_del_adjunto(documento, rol, sha256)
    almacen_ = almacen()
    if not almacen_.exists(ruta):
        almacen_.save(ruta, ContentFile(contenido))
    adjunto = Adjunto.objects.create(
        documento=documento, rol=rol, ruta=ruta, nombre_original=nombre[:255],
        sha256=sha256, tamano=len(contenido), subido_por=usuario,
        subido_por_nombre=nombre_de_usuario(usuario) if usuario_nombre is None else usuario_nombre,
    )
    if rol in Adjunto.ROLES_CON_OCR:
        _preparar_ocr(adjunto, encolar=encolar)
    datos = {"adjunto": nombre, "origen": origen, "rol": rol, "sha256": sha256, "tamano": len(contenido)}
    if duplicado:
        datos["duplicado_de"] = duplicado.documento.folio or str(duplicado.documento_id)
    if concluir and rol == Adjunto.Rol.EVIDENCIA and documento.estado == Documento.Estado.ENTREGADO:
        documento.estado = Documento.Estado.CONCLUIDO
        documento.save()
        datos.update(estado_anterior=Documento.Estado.ENTREGADO, estado_nuevo=documento.estado)
    _historial(documento, HistorialDocumento.Accion.ADJUNTADO, usuario, datos, usuario_nombre)
    return adjunto, duplicado


def _preparar_ocr(adjunto, *, encolar=True):
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
    if encolar:
        transaction.on_commit(lambda: encolar_tarea(TAREA_OCR, str(adjunto.pk), timeout=TIMEOUT_TAREA))


CAMPOS_EDITABLES = ("contraparte", "contraparte_dependencia_uuid", "asunto", "fecha")


def _valor_historial(valor):
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return getattr(valor, "nombre", valor)


@transaction.atomic
def editar_documento(documento, *, usuario, cambios, motivo=""):
    """Corrige datos del documento y deja en el historial cada valor anterior y nuevo."""
    documento = Documento.objects.select_for_update().get(pk=documento.pk)
    if documento.estado == Documento.Estado.CANCELADO:
        raise ValidationError("Un documento cancelado no se puede editar.")
    if documento.sentido == Documento.Sentido.RECIBIDO:
        permitidos = CAMPOS_EDITABLES + ("folio",)
    else:
        permitidos = CAMPOS_EDITABLES + ("gestor",) + (("folio",) if documento.folio_manual else ())
    diferencias = {}
    for campo, nuevo in cambios.items():
        if campo not in permitidos:
            raise ValidationError(f"El campo '{campo}' no se puede editar.")
        actual = getattr(documento, campo)
        if isinstance(nuevo, str):
            nuevo = nuevo.strip()
        if nuevo != actual:
            if campo == "gestor":
                _validar_gestor(nuevo, documento.direccion, documento.sentido)
            if campo == "folio" and documento.sentido == Documento.Sentido.ENVIADO:
                if not nuevo:
                    raise ValidationError("El folio de un oficio enviado no puede quedar vacío.")
                if Documento.objects.filter(
                    direccion=documento.direccion, sentido=Documento.Sentido.ENVIADO, folio=nuevo
                ).exclude(pk=documento.pk).exists():
                    raise ValidationError(f"Ya existe un oficio enviado con el folio {nuevo} en esta dirección.")
            diferencias[campo] = (actual, nuevo)
    if not diferencias:
        raise ValidationError("No hay cambios que guardar.")
    if "fecha" in diferencias and documento.anio and diferencias["fecha"][1].year != documento.anio:
        raise ValidationError(f"La fecha debe seguir en {documento.anio}, el año del folio {documento.folio}.")
    for campo, (_, nuevo) in diferencias.items():
        setattr(documento, campo, nuevo)
    documento.save()
    _historial(documento, HistorialDocumento.Accion.EDITADO, usuario, {
        "cambios": {
            campo: {"antes": _valor_historial(antes), "despues": _valor_historial(despues)}
            for campo, (antes, despues) in diferencias.items()
            if campo != "contraparte_dependencia_uuid"
        },
        "motivo": (motivo or "").strip(),
    })
    return documento


@transaction.atomic
def quitar_adjunto(adjunto, *, usuario, motivo):
    """Retira un archivo subido por error. Queda registrado (quién, cuándo y por qué); el PDF no se destruye."""
    documento = Documento.objects.select_for_update().get(pk=adjunto.documento_id)
    adjunto = Adjunto.objects.get(pk=adjunto.pk)
    motivo = (motivo or "").strip()
    if len(motivo) < MOTIVO_MINIMO:
        raise ValidationError(f"El motivo debe tener al menos {MOTIVO_MINIMO} caracteres.")
    if adjunto.eliminado:
        raise ValidationError("El archivo ya fue quitado.")
    if documento.estado == Documento.Estado.CANCELADO:
        raise ValidationError("Un documento cancelado no se modifica.")
    Adjunto.objects.filter(pk=adjunto.pk).update(
        eliminado=True, eliminado_motivo=motivo, eliminado_en=timezone.now(),
        eliminado_por_nombre=nombre_de_usuario(usuario),
    )
    datos = {"adjunto": adjunto.nombre_original, "rol": adjunto.rol, "sha256": adjunto.sha256, "motivo": motivo}
    quedan_evidencias = documento.adjuntos.filter(rol=Adjunto.Rol.EVIDENCIA, eliminado=False).exists()
    if (adjunto.rol == Adjunto.Rol.EVIDENCIA and documento.estado == Documento.Estado.CONCLUIDO
            and documento.sentido == Documento.Sentido.ENVIADO and not quedan_evidencias):
        documento.estado = Documento.Estado.ENTREGADO
        documento.save()
        datos.update(estado_anterior=Documento.Estado.CONCLUIDO, estado_nuevo=documento.estado)
    _historial(documento, HistorialDocumento.Accion.QUITADO, usuario, datos)
    return Adjunto.objects.get(pk=adjunto.pk)
