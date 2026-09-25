import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import Bien, ClaseDocumento, Documento, HistorialBien, HistorialDocumento, Prestamo, PrestamoBien
from ..services import MOTIVO_MINIMO as MOTIVO_DE_EDICION, _historial, crear_documento
from . import bitacora


def _fecha(valor):
    return f"{valor:%d/%m/%Y}"


@transaction.atomic
def crear_vale(*, usuario, direccion, bienes, fecha_entrega, fecha_limite, contraparte,
               contraparte_dependencia_uuid=None, gestor=None, observaciones=""):
    """Genera el vale: un documento (con su folio automático) más el préstamo y los bienes que salen."""
    if not direccion.vales_habilitados:
        raise ValidationError("Esta dirección no tiene habilitados los vales de préstamo.")
    ids = [b.pk for b in bienes]
    if not ids:
        raise ValidationError("Elija al menos un bien.")
    if fecha_limite < fecha_entrega:
        raise ValidationError("La devolución límite no puede ser anterior a la entrega.")
    bloqueados = list(Bien.objects.select_for_update().filter(pk__in=ids).order_by("nombre", "identificador"))
    for bien in bloqueados:
        if bien.direccion_id != direccion.pk:
            raise ValidationError(f"El bien {bien} no pertenece a esta dirección.")
        if bien.is_deleted or not bien.is_active or bien.estado != Bien.Estado.DISPONIBLE:
            raise ValidationError(f"El bien {bien} no está disponible.")
        if PrestamoBien.objects.filter(bien=bien, abierto=True).exists():
            raise ValidationError(f"El bien {bien} ya está prestado.")
    nombres = [str(b) for b in bloqueados]
    asunto = f"Vale de préstamo: {'; '.join(nombres)}"[:300]
    documento = crear_documento(
        usuario=usuario, direccion=direccion, sentido=Documento.Sentido.ENVIADO, clase=ClaseDocumento.VALE_PRESTAMO,
        contraparte=contraparte, contraparte_dependencia_uuid=contraparte_dependencia_uuid, asunto=asunto,
        fecha=fecha_entrega, gestor=gestor, folio_automatico=True, desde_vale=True,
    )
    prestamo = Prestamo.objects.create(
        documento=documento, fecha_entrega=fecha_entrega, fecha_limite=fecha_limite, observaciones=observaciones.strip(),
    )
    try:
        with transaction.atomic():
            PrestamoBien.objects.bulk_create([PrestamoBien(prestamo=prestamo, bien=b) for b in bloqueados])
    except IntegrityError as error:
        raise ValidationError("Alguno de los bienes acaba de prestarse en otro vale.") from error
    _historial(documento, HistorialDocumento.Accion.PRESTAMO, usuario, {
        "resumen": f"Préstamo de {len(nombres)} bien(es) del {_fecha(fecha_entrega)} al {_fecha(fecha_limite)}",
        "bienes": nombres, "fecha_limite": fecha_limite.isoformat(),
    })
    for bien in bloqueados:
        bitacora.registrar(bien, HistorialBien.Accion.PRESTAMO, usuario, {
            "folio": documento.folio, "recibe": contraparte, "desde": fecha_entrega.isoformat(),
            "fecha_limite": fecha_limite.isoformat(),
        })
    return documento, prestamo


@transaction.atomic
def registrar_devolucion(prestamo, *, usuario, fecha=None, observaciones=""):
    """Devolución completa: los bienes quedan disponibles de nuevo."""
    prestamo = Prestamo.objects.select_for_update().select_related("documento").get(pk=prestamo.pk)
    if prestamo.documento.estado == Documento.Estado.CANCELADO:
        raise ValidationError("El vale está cancelado; sus bienes ya se liberaron.")
    if prestamo.fecha_devolucion:
        raise ValidationError("Este préstamo ya fue devuelto.")
    fecha = fecha or timezone.localdate()
    if fecha < prestamo.fecha_entrega:
        raise ValidationError("La devolución no puede ser anterior a la entrega.")
    if fecha > timezone.localdate():
        raise ValidationError("La fecha de devolución no puede ser futura.")
    prestamo.fecha_devolucion = fecha
    prestamo.observaciones_devolucion = (observaciones or "").strip()
    prestamo.save()
    nombres = [str(r.bien) for r in prestamo.renglones.select_related("bien")]
    prestamo.renglones.filter(abierto=True).update(abierto=False)
    _historial(prestamo.documento, HistorialDocumento.Accion.PRESTAMO, usuario, {
        "resumen": f"Devolución completa el {_fecha(fecha)}", "bienes": nombres,
        "devolucion": fecha.isoformat(), "observaciones": prestamo.observaciones_devolucion,
    })
    for renglon in prestamo.renglones.select_related("bien"):
        bitacora.registrar(renglon.bien, HistorialBien.Accion.DEVOLUCION, usuario, {
            "folio": prestamo.documento.folio, "recibe": prestamo.documento.contraparte,
            "devolucion": fecha.isoformat(), "observaciones": prestamo.observaciones_devolucion,
        })
    return prestamo


ESTADOS_CON_MOTIVO = (Bien.Estado.EN_REPARACION, Bien.Estado.BAJA)
MOTIVO_MINIMO = 5
CAMPOS_BIEN = ("nombre", "marca_modelo", "identificador", "folio_inventario", "descripcion", "estado")


def foto_bien(bien):
    return {campo: getattr(bien, campo) for campo in CAMPOS_BIEN}


def exigir_motivo_de_estado(estado_anterior, estado_nuevo, motivo):
    """Reparación y baja exigen motivo; volver a disponible lo deja opcional."""
    if estado_nuevo != estado_anterior and estado_nuevo in ESTADOS_CON_MOTIVO and len((motivo or "").strip()) < MOTIVO_MINIMO:
        raise ValidationError(f"Indique el motivo (mínimo {MOTIVO_MINIMO} caracteres) para pasar el bien a reparación o baja.")


@transaction.atomic
def registrar_alta_bien(bien, *, usuario):
    return bitacora.registrar(bien, HistorialBien.Accion.ALTA, usuario, foto_bien(bien))


@transaction.atomic
def registrar_cambios_bien(bien, antes, *, usuario, motivo=""):
    """Deja en la bitácora qué cambió (valor anterior y nuevo) y el motivo, si lo hay."""
    cambios = {
        campo: {"antes": antes[campo], "despues": getattr(bien, campo)}
        for campo in CAMPOS_BIEN if antes[campo] != getattr(bien, campo)
    }
    if not cambios:
        return None
    exigir_motivo_de_estado(antes["estado"], bien.estado, motivo)
    accion = HistorialBien.Accion.ESTADO if "estado" in cambios else HistorialBien.Accion.EDITADO
    return bitacora.registrar(bien, accion, usuario, {"cambios": cambios, "motivo": (motivo or "").strip()})


@transaction.atomic
def editar_vale(prestamo, *, usuario, fecha_entrega, fecha_limite, observaciones, contraparte,
                contraparte_dependencia_uuid=None, motivo=""):
    """Corrige fechas, quién recibe y observaciones de un vale. Los bienes no cambian: se cancela y se emite otro.

    La serie o el nombre de un bien se corrigen en el propio bien, y el vale los muestra al imprimirse.
    """
    from ..soporte.services import edicion_exige_motivo

    prestamo = Prestamo.objects.select_for_update().select_related("documento").get(pk=prestamo.pk)
    documento = prestamo.documento
    if documento.estado == Documento.Estado.CANCELADO:
        raise ValidationError("Un vale cancelado no se puede editar.")
    if fecha_limite < fecha_entrega:
        raise ValidationError("La devolución límite no puede ser anterior a la entrega.")
    if documento.anio and fecha_entrega.year != documento.anio:
        raise ValidationError(f"La entrega debe seguir en {documento.anio}, el año del folio {documento.folio}.")
    if prestamo.fecha_devolucion and fecha_entrega > prestamo.fecha_devolucion:
        raise ValidationError("La entrega no puede ser posterior a la devolución ya registrada.")
    contraparte = (contraparte or "").strip()
    if not contraparte:
        raise ValidationError("Indique quién recibe.")
    cambios = {}
    for nombre, antes, despues in (
        ("Fecha de entrega", prestamo.fecha_entrega, fecha_entrega), ("Devolución límite", prestamo.fecha_limite, fecha_limite),
        ("Recibe", documento.contraparte, contraparte), ("Observaciones", prestamo.observaciones, (observaciones or "").strip()),
    ):
        if antes != despues:
            cambios[nombre] = {
                "antes": _fecha(antes) if isinstance(antes, datetime.date) else antes,
                "despues": _fecha(despues) if isinstance(despues, datetime.date) else despues,
            }
    if not cambios:
        raise ValidationError("No hay cambios que guardar.")
    if edicion_exige_motivo(documento) and len((motivo or "").strip()) < MOTIVO_DE_EDICION:
        raise ValidationError(
            f"El vale ya se firmó o entregó: indique el motivo de la corrección (mínimo {MOTIVO_DE_EDICION} caracteres)."
        )
    prestamo.fecha_entrega, prestamo.fecha_limite = fecha_entrega, fecha_limite
    prestamo.observaciones = (observaciones or "").strip()
    prestamo.save()
    documento.fecha, documento.contraparte = fecha_entrega, contraparte
    documento.contraparte_dependencia_uuid = contraparte_dependencia_uuid
    documento.save()
    _historial(documento, HistorialDocumento.Accion.EDITADO, usuario, {"cambios": cambios, "motivo": (motivo or "").strip()})
    return prestamo
