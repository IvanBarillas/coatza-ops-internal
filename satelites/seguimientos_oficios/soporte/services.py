from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import Bien, ClaseDocumento, Dictamen, DictamenBien, Documento, HistorialBien, HistorialDocumento, PrestamoBien
from ..services import _historial, crear_documento
from ..prestamos import bitacora

RECOMENDACIONES = (("mantenimiento", "Mantenimiento"), ("reasignacion", "Reasignación"), ("baja", "Baja"))
CLASIFICACIONES = (
    ("obsolescencia", "Con obsolescencia."),
    ("funcional_sin_uso", "Aún es funcional, pero ya no se requiere para la prestación del servicio."),
    ("no_reparable", "Se han descompuesto y no son susceptibles de reparación, ya que esta no resulta rentable."),
    ("desecho", "Son desechos."),
    ("robo_extravio", "Por robo o extravío."),
    ("otro", "Otros (causa distinta a las señaladas)."),
)
DISPOSICIONES = (
    ("enajenacion", "Enajenación onerosa"), ("donacion", "Donación"), ("destruccion", "Destrucción"),
    ("otro", "Otro (bienes de control temporal y posterior destrucción)"),
)
CLASES_DE_SOPORTE = (ClaseDocumento.DIAGNOSTICO_TECNICO, ClaseDocumento.DICTAMEN_ALTA, ClaseDocumento.DICTAMEN_BAJA)
ETIQUETAS = dict(RECOMENDACIONES) | dict(CLASIFICACIONES) | dict(DISPOSICIONES)


def _emitir(*, clase, usuario, direccion, contraparte, asunto, ticket, elaboro_nombre, elaboro_cargo, autoriza_nombre,
            autoriza_cargo, datos, equipos, contraparte_dependencia_uuid=None, fecha=None):
    """Crea el documento (folio automático), su contenido y los equipos que ampara."""
    if not direccion.soporte_habilitado:
        raise ValidationError("Esta dirección no tiene habilitado el soporte técnico.")
    fecha = fecha or timezone.localdate()
    documento = crear_documento(
        usuario=usuario, direccion=direccion, sentido=Documento.Sentido.ENVIADO, clase=clase,
        contraparte=contraparte, contraparte_dependencia_uuid=contraparte_dependencia_uuid,
        asunto=asunto[:300], fecha=fecha, folio_automatico=True,
    )
    dictamen = Dictamen.objects.create(
        documento=documento, ticket=(ticket or "").strip(), elaboro_nombre=elaboro_nombre, elaboro_cargo=elaboro_cargo,
        autoriza_nombre=(autoriza_nombre or "").strip(), autoriza_cargo=(autoriza_cargo or "").strip(), datos=datos,
    )
    DictamenBien.objects.bulk_create([
        DictamenBien(dictamen=dictamen, orden=i, bien=e.get("bien"), equipo=e["equipo"], marca_modelo=e.get("marca_modelo", ""),
                     serie=e.get("serie", ""), folio_inventario=e.get("folio_inventario", ""), departamento=e.get("departamento", ""))
        for i, e in enumerate(equipos)
    ])
    _historial(documento, HistorialDocumento.Accion.EDITADO, usuario, {
        "resumen": f"Emitido: {documento.get_clase_display()} con {len(equipos)} equipo(s)", "ticket": dictamen.ticket,
    })
    return documento, dictamen


def _validar_equipos(equipos, minimo=1):
    if len(equipos) < minimo:
        raise ValidationError("Agregue al menos un equipo.")
    for equipo in equipos:
        if not (equipo.get("equipo") or "").strip():
            raise ValidationError("Cada equipo necesita al menos su descripción.")


@transaction.atomic
def emitir_diagnostico(*, usuario, direccion, solicitante, ticket, equipo, datos, elaboro_nombre, elaboro_cargo,
                       autoriza_nombre="", autoriza_cargo=""):
    _validar_equipos([equipo])
    if datos.get("recomendacion") not in dict(RECOMENDACIONES):
        raise ValidationError("Elija la recomendación sobre el bien.")
    documento, dictamen = _emitir(
        clase=ClaseDocumento.DIAGNOSTICO_TECNICO, usuario=usuario, direccion=direccion, contraparte=solicitante,
        asunto=f"Diagnóstico técnico: {equipo['equipo']}", ticket=ticket, elaboro_nombre=elaboro_nombre,
        elaboro_cargo=elaboro_cargo, autoriza_nombre=autoriza_nombre, autoriza_cargo=autoriza_cargo, datos=datos,
        equipos=[equipo],
    )
    if equipo.get("bien"):
        bitacora.registrar(equipo["bien"], HistorialBien.Accion.DIAGNOSTICO, usuario, {
            "folio": documento.folio, "fallo": datos.get("fallo", ""),
            "recomendacion": ETIQUETAS[datos["recomendacion"]],
        })
    return documento, dictamen


@transaction.atomic
def emitir_baja(*, usuario, direccion, contraparte, ticket, equipos, datos, elaboro_nombre, elaboro_cargo,
                autoriza_nombre, autoriza_cargo, contraparte_dependencia_uuid=None):
    """Dictamen de baja: los equipos del catálogo pasan a baja, con su bitácora."""
    _validar_equipos(equipos)
    if datos.get("clasificacion") not in dict(CLASIFICACIONES):
        raise ValidationError("Elija la clasificación de no utilidad.")
    if datos.get("disposicion") not in dict(DISPOSICIONES):
        raise ValidationError("Elija la recomendación de disposición final.")
    ids = [e["bien"].pk for e in equipos if e.get("bien")]
    if len(ids) != len(set(ids)):
        raise ValidationError("Un mismo bien no puede repetirse en el dictamen.")
    bloqueados = {b.pk: b for b in Bien.objects.select_for_update().filter(pk__in=ids)}
    for pk in ids:
        bien = bloqueados[pk]
        if bien.direccion_id != direccion.pk:
            raise ValidationError(f"El bien {bien} no pertenece a esta dirección.")
        if bien.estado == Bien.Estado.BAJA:
            raise ValidationError(f"El bien {bien} ya está dado de baja.")
        if PrestamoBien.objects.filter(bien=bien, abierto=True).exists():
            raise ValidationError(f"El bien {bien} está prestado: registre primero la devolución del vale.")
    documento, dictamen = _emitir(
        clase=ClaseDocumento.DICTAMEN_BAJA, usuario=usuario, direccion=direccion, contraparte=contraparte,
        contraparte_dependencia_uuid=contraparte_dependencia_uuid,
        asunto=f"Dictamen de baja de {len(equipos)} bien(es): {'; '.join(e['equipo'] for e in equipos)}",
        ticket=ticket, elaboro_nombre=elaboro_nombre, elaboro_cargo=elaboro_cargo, autoriza_nombre=autoriza_nombre,
        autoriza_cargo=autoriza_cargo, datos=datos, equipos=equipos,
    )
    for pk in ids:
        bien = bloqueados[pk]
        anterior = bien.estado
        bien.estado = Bien.Estado.BAJA
        bien.save(update_fields=["estado", "updated_at"])
        bitacora.registrar(bien, HistorialBien.Accion.DICTAMEN, usuario, {
            "folio": documento.folio, "cambios": {"estado": {"antes": anterior, "despues": bien.estado}},
            "motivo": f"Dictamen de baja {documento.folio}: {ETIQUETAS[datos['clasificacion']]}",
        })
    return documento, dictamen


@transaction.atomic
def emitir_alta(*, usuario, direccion, contraparte, ticket, datos, elaboro_nombre, elaboro_cargo, autoriza_nombre,
                autoriza_cargo, contraparte_dependencia_uuid=None):
    """Dictamen de alta: solo documenta la solicitud; no crea el bien."""
    for campo, nombre in (("solicitud", "la solicitud"), ("justificacion", "la justificación"), ("dictamen", "el dictamen")):
        if not (datos.get(campo) or "").strip():
            raise ValidationError(f"Escriba {nombre}.")
    return _emitir(
        clase=ClaseDocumento.DICTAMEN_ALTA, usuario=usuario, direccion=direccion, contraparte=contraparte,
        contraparte_dependencia_uuid=contraparte_dependencia_uuid, asunto=f"Dictamen de alta para {contraparte}",
        ticket=ticket, elaboro_nombre=elaboro_nombre, elaboro_cargo=elaboro_cargo, autoriza_nombre=autoriza_nombre,
        autoriza_cargo=autoriza_cargo, datos=datos, equipos=[],
    )
