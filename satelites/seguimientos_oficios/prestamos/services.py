import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import Bien, ClaseDocumento, Documento, HistorialDocumento, Prestamo, PrestamoBien
from ..services import _historial, crear_documento


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
    return prestamo
