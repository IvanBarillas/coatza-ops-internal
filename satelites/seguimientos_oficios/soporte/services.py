from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import Adjunto, Bien, ClaseDocumento, Dictamen, DictamenBien, Documento, HistorialBien, HistorialDocumento, PrestamoBien
from ..services import MOTIVO_MINIMO, _historial, _validar_gestor, crear_documento
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
            autoriza_cargo, datos, equipos, contraparte_dependencia_uuid=None, fecha=None, gestor=None):
    """Crea el documento (folio automático), su contenido y los equipos que ampara."""
    if not direccion.soporte_habilitado:
        raise ValidationError("Esta dirección no tiene habilitado el soporte técnico.")
    fecha = fecha or timezone.localdate()
    documento = crear_documento(
        usuario=usuario, direccion=direccion, sentido=Documento.Sentido.ENVIADO, clase=clase,
        contraparte=contraparte, contraparte_dependencia_uuid=contraparte_dependencia_uuid,
        asunto=asunto[:300], fecha=fecha, folio_automatico=True, gestor=gestor,
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


def asunto_de(clase, contraparte, equipos):
    nombres = "; ".join(e["equipo"] for e in equipos)
    if clase == ClaseDocumento.DIAGNOSTICO_TECNICO:
        return f"Diagnóstico técnico: {nombres}"
    if clase == ClaseDocumento.DICTAMEN_BAJA:
        return f"Dictamen de baja de {len(equipos)} bien(es): {nombres}"
    return f"Dictamen de alta para {contraparte}"


def _validar_equipos(equipos, minimo=1):
    if len(equipos) < minimo:
        raise ValidationError("Agregue al menos un equipo.")
    for equipo in equipos:
        if not (equipo.get("equipo") or "").strip():
            raise ValidationError("Cada equipo necesita al menos su descripción.")


@transaction.atomic
def emitir_diagnostico(*, usuario, direccion, solicitante, ticket, equipo, datos, elaboro_nombre, elaboro_cargo,
                       autoriza_nombre="", autoriza_cargo="", gestor=None):
    _validar_equipos([equipo])
    if datos.get("recomendacion") not in dict(RECOMENDACIONES):
        raise ValidationError("Elija la recomendación sobre el bien.")
    documento, dictamen = _emitir(
        clase=ClaseDocumento.DIAGNOSTICO_TECNICO, usuario=usuario, direccion=direccion, contraparte=solicitante,
        asunto=asunto_de(ClaseDocumento.DIAGNOSTICO_TECNICO, solicitante, [equipo]), ticket=ticket, elaboro_nombre=elaboro_nombre,
        elaboro_cargo=elaboro_cargo, autoriza_nombre=autoriza_nombre, autoriza_cargo=autoriza_cargo, datos=datos,
        equipos=[equipo], gestor=gestor,
    )
    if equipo.get("bien"):
        bitacora.registrar(equipo["bien"], HistorialBien.Accion.DIAGNOSTICO, usuario, {
            "folio": documento.folio, "fallo": datos.get("fallo", ""),
            "recomendacion": ETIQUETAS[datos["recomendacion"]],
        })
    return documento, dictamen


@transaction.atomic
def emitir_baja(*, usuario, direccion, contraparte, ticket, equipos, datos, elaboro_nombre, elaboro_cargo,
                autoriza_nombre, autoriza_cargo, contraparte_dependencia_uuid=None, gestor=None):
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
        asunto=asunto_de(ClaseDocumento.DICTAMEN_BAJA, contraparte, equipos),
        ticket=ticket, elaboro_nombre=elaboro_nombre, elaboro_cargo=elaboro_cargo, autoriza_nombre=autoriza_nombre,
        autoriza_cargo=autoriza_cargo, datos=datos, equipos=equipos, gestor=gestor,
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
                autoriza_cargo, contraparte_dependencia_uuid=None, gestor=None):
    """Dictamen de alta: solo documenta la solicitud; no crea el bien."""
    for campo, nombre in (("solicitud", "la solicitud"), ("justificacion", "la justificación"), ("dictamen", "el dictamen")):
        if not (datos.get(campo) or "").strip():
            raise ValidationError(f"Escriba {nombre}.")
    return _emitir(
        clase=ClaseDocumento.DICTAMEN_ALTA, usuario=usuario, direccion=direccion, contraparte=contraparte,
        contraparte_dependencia_uuid=contraparte_dependencia_uuid, asunto=asunto_de(ClaseDocumento.DICTAMEN_ALTA, contraparte, []),
        ticket=ticket, elaboro_nombre=elaboro_nombre, elaboro_cargo=elaboro_cargo, autoriza_nombre=autoriza_nombre,
        autoriza_cargo=autoriza_cargo, datos=datos, equipos=[], gestor=gestor,
    )


ETIQUETAS_CAMPOS = {
    "ticket": "Ticket", "elaboro_cargo": "Cargo de quien elabora", "autoriza_nombre": "Autoriza (nombre)",
    "autoriza_cargo": "Autoriza (cargo)", "contraparte": "Solicitante / dirigido a", "fecha_recibido": "Fecha de recibido",
    "tipo_bien": "Tipo de bien", "fallo": "Fallo", "causa": "Causa", "solucion": "Solución", "observaciones": "Observaciones",
    "recomendacion": "Recomendación", "solicito": "Solicitó", "diagnostico": "Diagnóstico", "clasificacion": "Clasificación",
    "disposicion": "Disposición final", "solicitud": "Solicitud", "justificacion": "Justificación", "dictamen": "Dictamen",
}
CAMPOS_EQUIPO = ("equipo", "marca_modelo", "serie", "folio_inventario", "departamento")
ETIQUETAS_EQUIPO = {
    "equipo": "equipo", "marca_modelo": "marca y modelo", "serie": "serie", "folio_inventario": "folio de inventario",
    "departamento": "departamento",
}


def edicion_exige_motivo(documento):
    """Con el documento ya firmado (archivo firmado, entregado o concluido) toda corrección necesita motivo."""
    return (
        documento.estado in (Documento.Estado.ENTREGADO, Documento.Estado.CONCLUIDO)
        or documento.adjuntos.filter(rol=Adjunto.Rol.FIRMADO, eliminado=False).exists()
    )


def exigir_motivo_de_edicion(documento, motivo):
    if edicion_exige_motivo(documento) and len((motivo or "").strip()) < MOTIVO_MINIMO:
        raise ValidationError(
            f"El documento ya se firmó o entregó: indique el motivo de la corrección (mínimo {MOTIVO_MINIMO} caracteres)."
        )


def _legible(valor):
    return ETIQUETAS.get(valor, valor)


SIN_CAMBIO = object()


@transaction.atomic
def editar_dictamen(dictamen, *, usuario, campos, datos, equipos, contraparte=None, contraparte_dependencia_uuid=None, motivo="",
                    gestor=SIN_CAMBIO):
    """Corrige un diagnóstico o dictamen ya emitido y deja en el historial cada valor anterior y nuevo.

    No cambia el folio, la dirección, la clase ni qué bienes ampara (la baja ya movió su estado): para eso se cancela
    y se emite otro. `equipos` es {id del renglón: textos nuevos}; debe traer exactamente los renglones existentes.
    """
    dictamen = Dictamen.objects.select_for_update().select_related("documento").get(pk=dictamen.pk)
    documento = dictamen.documento
    if documento.estado == Documento.Estado.CANCELADO:
        raise ValidationError("Un documento cancelado no se puede editar.")
    clase = documento.clase
    renglones = {str(r.pk): r for r in dictamen.equipos.all()}
    if set(str(k) for k in equipos) != set(renglones):
        raise ValidationError("Los equipos del documento no se pueden agregar ni quitar: cancele y emita otro.")
    nuevos = {str(k): v for k, v in equipos.items()}
    for fila in nuevos.values():
        if not (fila.get("equipo") or "").strip():
            raise ValidationError("Cada equipo necesita al menos su descripción.")
    combinado = {**dictamen.datos, **datos}
    if clase == ClaseDocumento.DIAGNOSTICO_TECNICO and combinado.get("recomendacion") not in dict(RECOMENDACIONES):
        raise ValidationError("Elija la recomendación sobre el bien.")
    if clase == ClaseDocumento.DICTAMEN_BAJA:
        if combinado.get("clasificacion") not in dict(CLASIFICACIONES):
            raise ValidationError("Elija la clasificación de no utilidad.")
        if combinado.get("disposicion") not in dict(DISPOSICIONES):
            raise ValidationError("Elija la recomendación de disposición final.")
    if clase == ClaseDocumento.DICTAMEN_ALTA:
        for campo, nombre in (("solicitud", "la solicitud"), ("justificacion", "la justificación"), ("dictamen", "el dictamen")):
            if not (combinado.get(campo) or "").strip():
                raise ValidationError(f"Escriba {nombre}.")
    cambios = {}

    def anotar(nombre, antes, despues):
        if (antes or "") != (despues or ""):
            cambios[nombre] = {"antes": _legible(antes) or "", "despues": _legible(despues) or ""}

    for campo, nuevo in campos.items():
        nuevo = (nuevo or "").strip()
        anotar(ETIQUETAS_CAMPOS[campo], getattr(dictamen, campo), nuevo)
        setattr(dictamen, campo, nuevo)
    if contraparte is not None and clase != ClaseDocumento.DIAGNOSTICO_TECNICO:
        anotar(ETIQUETAS_CAMPOS["contraparte"], documento.contraparte, contraparte)
        documento.contraparte = contraparte
        documento.contraparte_dependencia_uuid = contraparte_dependencia_uuid
    if clase == ClaseDocumento.DIAGNOSTICO_TECNICO and contraparte is not None:
        anotar(ETIQUETAS_CAMPOS["contraparte"], documento.contraparte, contraparte)
        documento.contraparte = contraparte
    nuevos_datos = dict(dictamen.datos)
    for clave, nuevo in datos.items():
        nuevo = (nuevo or "").strip() if isinstance(nuevo, str) else nuevo
        anotar(ETIQUETAS_CAMPOS.get(clave, clave), dictamen.datos.get(clave), nuevo)
        nuevos_datos[clave] = nuevo
    dictamen.datos = nuevos_datos
    for indice, (pk, renglon) in enumerate(renglones.items(), start=1):
        for campo in CAMPOS_EQUIPO:
            nuevo = (nuevos[pk].get(campo) or "").strip()
            anotar(f"Equipo {indice}: {ETIQUETAS_EQUIPO[campo]}", getattr(renglon, campo), nuevo)
            setattr(renglon, campo, nuevo)
    if gestor is not SIN_CAMBIO and gestor != documento.gestor:
        _validar_gestor(gestor, documento.direccion, documento.sentido, documento.gestor)
        anotar("Gestor", documento.gestor.nombre if documento.gestor else "", gestor.nombre if gestor else "")
        documento.gestor = gestor
    if not cambios:
        raise ValidationError("No hay cambios que guardar.")
    exigir_motivo_de_edicion(documento, motivo)
    dictamen.save()
    for renglon in renglones.values():
        renglon.save()
    documento.asunto = asunto_de(clase, documento.contraparte, [{"equipo": r.equipo} for r in renglones.values()])[:300]
    documento.save()
    _historial(documento, HistorialDocumento.Accion.EDITADO, usuario, {"cambios": cambios, "motivo": (motivo or "").strip()})
    return documento, dictamen
