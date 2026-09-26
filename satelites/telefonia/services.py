import hashlib
import io

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone

from .integracion import nombre_de_usuario, telefono_de_usuario
from .models import Evidencia, Movimiento, Reporte, normalizar_identificador
from .storage import almacen, ruta_de_evidencia

MOTIVO_MINIMO = 5
COMENTARIO_MINIMO = 2
TAMANO_MAXIMO = 15 * 1024 * 1024
TIPOS_DE_ARCHIVO = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"), (b"\x89PNG\r\n\x1a\n", "image/png", "png"), (b"%PDF-", "application/pdf", "pdf"),
)
CAMPOS_EDITABLES = ("folio", "levantado", "detalle", "contacto_nombre", "contacto_telefono")
ETIQUETAS = {
    "folio": "Folio de Telmex", "levantado": "Levantado", "detalle": "Detalle", "contacto_nombre": "Contacto en sitio",
    "contacto_telefono": "Teléfono del contacto",
}


def _mov(reporte, tipo, usuario, texto="", datos=None):
    return Movimiento.objects.create(
        reporte=reporte, tipo=tipo, usuario=usuario, usuario_nombre=nombre_de_usuario(usuario), texto=texto, datos=datos or {},
    )


def _fecha(valor):
    return f"{valor:%d/%m/%Y}" if hasattr(valor, "strftime") else valor


def _validar_folio(folio, excluir=None):
    folio = " ".join((folio or "").split())
    if not folio:
        raise ValidationError("Escriba el folio que dio Telmex.")
    repetidos = Reporte.objects.filter(folio_normalizado=normalizar_identificador(folio))
    if excluir is not None:
        repetidos = repetidos.exclude(pk=excluir.pk)
    if repetidos.exists():
        raise ValidationError(f"Ya existe un reporte con el folio {folio}.")
    return folio


def _validar_fecha_levantado(fecha):
    if fecha > timezone.localdate():
        raise ValidationError("La fecha en que se levantó el reporte no puede ser futura.")


def _exigir_no_cancelado(reporte):
    reporte.refresh_from_db(fields=["estatus"])  # el objeto pudo quedar viejo: otro usuario pudo cancelarlo
    if reporte.estatus == Reporte.Estatus.CANCELADO:
        raise ValidationError("El reporte está cancelado.")


def reportes_abiertos_de(linea):
    return Reporte.objects.filter(linea=linea, estatus=Reporte.Estatus.PENDIENTE, is_deleted=False)


@transaction.atomic
def crear_reporte(*, usuario, linea, folio, levantado, detalle="", contacto_nombre="", contacto_telefono="", responsable=None):
    """Registra el reporte con el folio de Telmex. Si el contacto en sitio es un usuario (responsable) y no se
    escribieron sus datos, se toman de su cuenta."""
    if linea is None or linea.is_deleted or not linea.is_active:
        raise ValidationError("Elija una línea activa.")
    folio = _validar_folio(folio)
    _validar_fecha_levantado(levantado)
    contacto_nombre = (contacto_nombre or "").strip() or (nombre_de_usuario(responsable) if responsable else "")
    contacto_telefono = (contacto_telefono or "").strip() or (telefono_de_usuario(responsable) if responsable else "")
    if not contacto_nombre or not contacto_telefono:
        raise ValidationError("Indique el nombre y el teléfono del contacto en sitio: Telmex le marcará para validar.")
    try:
        with transaction.atomic():
            reporte = Reporte.objects.create(
                linea=linea, linea_texto=linea.identificador, sitio_texto=linea.sitio, folio=folio, levantado=levantado,
                detalle=(detalle or "").strip(), contacto_nombre=contacto_nombre, contacto_telefono=contacto_telefono,
                responsable=responsable, responsable_nombre=nombre_de_usuario(responsable), creado_por=usuario,
            )
    except IntegrityError as error:
        raise ValidationError(f"Ya existe un reporte con el folio {folio}.") from error
    _mov(reporte, Movimiento.Tipo.CREADO, usuario, datos={
        "folio": folio, "linea": linea.identificador, "sitio": linea.sitio, "contacto": f"{contacto_nombre} · {contacto_telefono}",
    })
    return reporte


@transaction.atomic
def comentar(reporte, *, usuario, texto):
    texto = (texto or "").strip()
    _exigir_no_cancelado(reporte)
    if len(texto) < COMENTARIO_MINIMO:
        raise ValidationError("Escriba el comentario.")
    return _mov(reporte, Movimiento.Tipo.COMENTARIO, usuario, texto=texto)


def _detectar_tipo(contenido):
    for firma, content_type, extension in TIPOS_DE_ARCHIVO:
        if contenido.startswith(firma):
            return content_type, extension
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


@transaction.atomic
def subir_evidencia(reporte, *, usuario, archivo, tipo=Evidencia.Tipo.FOTO):
    """Foto o captura del técnico (JPG, PNG, WebP o PDF). Se conserva tal cual, sin recomprimir."""
    _exigir_no_cancelado(reporte)
    if tipo not in Evidencia.Tipo.values:
        raise ValidationError("Tipo de evidencia no válido.")
    contenido = archivo.read()
    if not contenido:
        raise ValidationError("El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO:
        raise ValidationError("El archivo pesa más de 15 MB.")
    detectado = _detectar_tipo(contenido)
    if detectado is None:
        raise ValidationError("Formato no admitido: suba una foto JPG, PNG o WebP, o un PDF.")
    content_type, extension = detectado
    if content_type.startswith("image/"):
        try:
            from PIL import Image

            with Image.open(io.BytesIO(contenido)) as imagen:
                imagen.verify()
        except Exception as error:
            raise ValidationError("La imagen no es válida.") from error
    sha256 = hashlib.sha256(contenido).hexdigest()
    if reporte.evidencias.filter(sha256=sha256, is_deleted=False).exists():
        raise ValidationError("Ese archivo ya se subió a este reporte.")
    ruta = almacen().save(ruta_de_evidencia(reporte, tipo, sha256, extension), ContentFile(contenido))
    evidencia = Evidencia.objects.create(
        reporte=reporte, tipo=tipo, ruta=ruta, nombre_original=(getattr(archivo, "name", "") or "archivo")[:200],
        content_type=content_type, tamano=len(contenido), sha256=sha256, subido_por=usuario, subido_por_nombre=nombre_de_usuario(usuario),
    )
    _mov(reporte, Movimiento.Tipo.EVIDENCIA, usuario, datos={"evidencia": str(evidencia.pk), "tipo": evidencia.get_tipo_display(), "archivo": evidencia.nombre_original})
    return evidencia


@transaction.atomic
def marcar_atendido(reporte, *, usuario, fecha=None, comentario=""):
    reporte = Reporte.objects.select_for_update().get(pk=reporte.pk)
    if reporte.estatus != Reporte.Estatus.PENDIENTE:
        raise ValidationError("Solo un reporte pendiente se puede marcar como atendido.")
    fecha = fecha or timezone.localdate()
    if fecha > timezone.localdate():
        raise ValidationError("La fecha de atención no puede ser futura.")
    if fecha < reporte.levantado:
        raise ValidationError("La fecha de atención no puede ser anterior a la del reporte.")
    reporte.estatus, reporte.atendido = Reporte.Estatus.ATENDIDO, fecha
    reporte.save()
    _mov(reporte, Movimiento.Tipo.ATENDIDO, usuario, texto=(comentario or "").strip(), datos={"atendido": fecha.isoformat(), "dias": reporte.dias_abierto})
    return reporte


@transaction.atomic
def cancelar(reporte, *, usuario, motivo):
    reporte = Reporte.objects.select_for_update().get(pk=reporte.pk)
    motivo = (motivo or "").strip()
    if reporte.estatus != Reporte.Estatus.PENDIENTE:
        raise ValidationError("Solo un reporte pendiente se puede cancelar.")
    if len(motivo) < MOTIVO_MINIMO:
        raise ValidationError(f"Indique el motivo (mínimo {MOTIVO_MINIMO} caracteres).")
    reporte.estatus, reporte.motivo_cancelacion = Reporte.Estatus.CANCELADO, motivo
    reporte.save()
    _mov(reporte, Movimiento.Tipo.CANCELADO, usuario, texto=motivo)
    return reporte


@transaction.atomic
def reabrir(reporte, *, usuario, motivo):
    reporte = Reporte.objects.select_for_update().get(pk=reporte.pk)
    motivo = (motivo or "").strip()
    if reporte.estatus == Reporte.Estatus.PENDIENTE:
        raise ValidationError("El reporte ya está pendiente.")
    if len(motivo) < MOTIVO_MINIMO:
        raise ValidationError(f"Indique el motivo (mínimo {MOTIVO_MINIMO} caracteres).")
    anterior = reporte.estatus
    reporte.estatus, reporte.atendido, reporte.motivo_cancelacion = Reporte.Estatus.PENDIENTE, None, ""
    reporte.save()
    _mov(reporte, Movimiento.Tipo.REABIERTO, usuario, texto=motivo, datos={"antes": anterior})
    return reporte


@transaction.atomic
def asignar_responsable(reporte, *, usuario, responsable):
    reporte = Reporte.objects.select_for_update().get(pk=reporte.pk)
    _exigir_no_cancelado(reporte)
    if responsable == reporte.responsable:
        raise ValidationError("Ese ya es el responsable.")
    antes = reporte.responsable_nombre
    reporte.responsable, reporte.responsable_nombre = responsable, nombre_de_usuario(responsable)
    reporte.save()
    _mov(reporte, Movimiento.Tipo.RESPONSABLE, usuario, datos={"antes": antes or "—", "despues": reporte.responsable_nombre or "—"})
    return reporte


@transaction.atomic
def editar_reporte(reporte, *, usuario, cambios, motivo=""):
    """Corrige datos capturados (folio, fecha, detalle, contacto). Deja el valor anterior y el nuevo en la bitácora."""
    reporte = Reporte.objects.select_for_update().get(pk=reporte.pk)
    _exigir_no_cancelado(reporte)
    diferencias = {}
    for campo, nuevo in cambios.items():
        if campo not in CAMPOS_EDITABLES:
            raise ValidationError(f"El campo '{campo}' no se puede editar.")
        if isinstance(nuevo, str):
            nuevo = " ".join(nuevo.split()) if campo != "detalle" else nuevo.strip()
        actual = getattr(reporte, campo)
        if nuevo == actual:
            continue
        if campo == "folio":
            nuevo = _validar_folio(nuevo, excluir=reporte)
        if campo == "levantado":
            _validar_fecha_levantado(nuevo)
            if reporte.atendido and nuevo > reporte.atendido:
                raise ValidationError("El reporte no puede levantarse después de la fecha en que se atendió.")
        if campo in ("contacto_nombre", "contacto_telefono") and not nuevo:
            raise ValidationError("El contacto en sitio necesita nombre y teléfono.")
        diferencias[campo] = (actual, nuevo)
    if not diferencias:
        raise ValidationError("No hay cambios que guardar.")
    for campo, (_, nuevo) in diferencias.items():
        setattr(reporte, campo, nuevo)
    reporte.save()
    _mov(reporte, Movimiento.Tipo.EDITADO, usuario, texto=(motivo or "").strip(), datos={"cambios": {
        ETIQUETAS[c]: {"antes": _fecha(a) or "", "despues": _fecha(d) or ""} for c, (a, d) in diferencias.items()
    }})
    return reporte
