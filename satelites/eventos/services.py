"""Reglas de los eventos. Nada bloquea por empalmes de técnicos: se avisa (los eventos se reservan con anticipación)."""
import calendar as pycal
import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .integracion import nombre_de_usuario
from .models import Asignacion, Bitacora, Evento, TramiteLinea, ValeSalida

E = Evento.Estatus


def _bitacora(evento, usuario, accion, detalle=""):
    return Bitacora.objects.create(evento=evento, usuario=usuario, usuario_nombre=nombre_de_usuario(usuario), accion=accion, detalle=detalle)


def _fmt(momento):
    return timezone.localtime(momento).strftime("%d/%m/%Y %H:%M")


def _exigir_abierto(evento):
    if not evento.abierto:
        raise ValidationError("El evento ya está %s: no admite cambios." % evento.get_estatus_display().lower())


def _validar_fechas(inicio, fin):
    if not inicio or not fin or fin <= inicio:
        raise ValidationError("El fin del evento debe ser posterior al inicio.")


# ---- evento ------------------------------------------------------------------------------------------------------

@transaction.atomic
def crear_evento(*, usuario, nombre, lugar, inicio, fin, descripcion="", ticket=""):
    _validar_fechas(inicio, fin)
    evento = Evento.objects.create(
        nombre=nombre.strip(), lugar=lugar.strip(), inicio=inicio, fin=fin, descripcion=descripcion.strip(), ticket=ticket.strip(), creado_por=usuario,
    )
    _bitacora(evento, usuario, "creado", f"{_fmt(inicio)} a {_fmt(fin)} · {evento.lugar}")
    return evento


@transaction.atomic
def editar_evento(evento, *, usuario, nombre, lugar, inicio, fin, descripcion="", ticket=""):
    _exigir_abierto(evento)
    _validar_fechas(inicio, fin)
    cambios = [
        etiqueta for etiqueta, antes, despues in (
            ("nombre", evento.nombre, nombre.strip()), ("lugar", evento.lugar, lugar.strip()), ("inicio", evento.inicio, inicio),
            ("fin", evento.fin, fin), ("descripción", evento.descripcion, descripcion.strip()), ("ticket", evento.ticket, ticket.strip()),
        ) if antes != despues
    ]
    evento.nombre, evento.lugar, evento.inicio, evento.fin = nombre.strip(), lugar.strip(), inicio, fin
    evento.descripcion, evento.ticket = descripcion.strip(), ticket.strip()
    evento.save()
    if cambios:
        _bitacora(evento, usuario, "editado", "Cambió: " + ", ".join(cambios))
    return evento


@transaction.atomic
def iniciar_evento(evento, *, usuario):
    if evento.estatus != E.PROGRAMADO:
        raise ValidationError("Solo un evento programado puede iniciarse.")
    evento.estatus = E.EN_CURSO
    evento.save(update_fields=["estatus", "updated_at"])
    _bitacora(evento, usuario, "iniciado")


@transaction.atomic
def concluir_evento(evento, *, usuario, notas=""):
    if not evento.abierto:
        raise ValidationError("El evento ya está %s." % evento.get_estatus_display().lower())
    evento.estatus, evento.notas_cierre = E.CONCLUIDO, notas.strip()
    evento.save(update_fields=["estatus", "notas_cierre", "updated_at"])
    _bitacora(evento, usuario, "concluido", notas.strip())


@transaction.atomic
def cancelar_evento(evento, *, usuario, motivo):
    _exigir_abierto(evento)
    if len((motivo or "").strip()) < 5:
        raise ValidationError("Escriba el motivo de la cancelación (mínimo 5 caracteres).")
    evento.estatus, evento.motivo_cancelacion = E.CANCELADO, motivo.strip()
    evento.save(update_fields=["estatus", "motivo_cancelacion", "updated_at"])
    _bitacora(evento, usuario, "cancelado", motivo.strip())


# ---- técnicos ----------------------------------------------------------------------------------------------------

def empalmes(tecnico, desde, hasta, *, excluir=None):
    """Asignaciones del técnico en otros eventos abiertos que se traslapan con el tramo."""
    consulta = Asignacion.objects.filter(
        tecnico=tecnico, evento__estatus__in=(E.PROGRAMADO, E.EN_CURSO), desde__lt=hasta, hasta__gt=desde,
    ).select_related("evento")
    if excluir is not None:
        consulta = consulta.exclude(evento=excluir)
    return list(consulta.order_by("desde"))


@transaction.atomic
def asignar_tecnico(evento, *, usuario, tecnico, desde=None, hasta=None, nota=""):
    """Devuelve (asignación, avisos). Sin fechas, el técnico cubre todo el evento."""
    _exigir_abierto(evento)
    desde, hasta = desde or evento.inicio, hasta or evento.fin
    if hasta <= desde:
        raise ValidationError("El tramo debe terminar después de empezar.")
    if not getattr(tecnico, "is_active", False):
        raise ValidationError("El técnico no está activo.")
    if evento.asignaciones.filter(tecnico=tecnico, desde__lt=hasta, hasta__gt=desde).exists():
        raise ValidationError("%s ya tiene un tramo que se traslapa en este evento." % nombre_de_usuario(tecnico))
    asignacion = Asignacion.objects.create(
        evento=evento, tecnico=tecnico, tecnico_nombre=nombre_de_usuario(tecnico), desde=desde, hasta=hasta, nota=nota.strip(),
    )
    avisos = [
        f"{asignacion.tecnico_nombre} ya está en «{o.evento.nombre}» ({_fmt(o.desde)} a {_fmt(o.hasta)}): se empalma."
        for o in empalmes(tecnico, desde, hasta, excluir=evento)
    ]
    _bitacora(evento, usuario, "tecnico_agregado", f"{asignacion.tecnico_nombre}: {_fmt(desde)} a {_fmt(hasta)}")
    return asignacion, avisos


@transaction.atomic
def quitar_tecnico(asignacion, *, usuario):
    evento = asignacion.evento
    _exigir_abierto(evento)
    asignacion.delete()
    _bitacora(evento, usuario, "tecnico_quitado", f"{asignacion.tecnico_nombre}: {_fmt(asignacion.desde)} a {_fmt(asignacion.hasta)}")


# ---- vales, telefonía y notas ------------------------------------------------------------------------------------

@transaction.atomic
def vincular_vale(evento, *, usuario, referencia, nota=""):
    _exigir_abierto(evento)
    referencia = (referencia or "").strip()
    if not referencia:
        raise ValidationError("Escriba el número o UUID del vale.")
    if evento.vales.filter(referencia__iexact=referencia).exists():
        raise ValidationError("Ese vale ya está vinculado al evento.")
    vale = ValeSalida.objects.create(evento=evento, referencia=referencia, nota=nota.strip())
    _bitacora(evento, usuario, "vale_vinculado", referencia)
    return vale


@transaction.atomic
def desvincular_vale(vale, *, usuario):
    _exigir_abierto(vale.evento)
    vale.delete()
    _bitacora(vale.evento, usuario, "vale_desvinculado", vale.referencia)


@transaction.atomic
def agregar_tramite(evento, *, usuario, tipo, descripcion, referencia=""):
    _exigir_abierto(evento)
    if not (descripcion or "").strip():
        raise ValidationError("Describa el trámite.")
    tramite = TramiteLinea.objects.create(evento=evento, tipo=tipo, descripcion=descripcion.strip(), referencia=referencia.strip())
    _bitacora(evento, usuario, "tramite_agregado", f"{tramite.get_tipo_display()}: {tramite.descripcion}")
    return tramite


@transaction.atomic
def cambiar_estado_tramite(tramite, *, usuario, estado):
    if estado not in TramiteLinea.Estado.values:
        raise ValidationError("Estado de trámite no válido.")
    tramite.estado = estado
    tramite.save(update_fields=["estado", "updated_at"])
    _bitacora(tramite.evento, usuario, "tramite_estado", f"{tramite.descripcion}: {tramite.get_estado_display()}")


@transaction.atomic
def quitar_tramite(tramite, *, usuario):
    _exigir_abierto(tramite.evento)
    tramite.delete()
    _bitacora(tramite.evento, usuario, "tramite_quitado", tramite.descripcion)


def agregar_nota(evento, *, usuario, texto):
    if not (texto or "").strip():
        raise ValidationError("Escriba la nota.")
    return _bitacora(evento, usuario, "nota", texto.strip())


# ---- calendario --------------------------------------------------------------------------------------------------

def _dia(momento):
    return timezone.localtime(momento).date()


def calendario_mes(anio, mes, tecnico_id=None):
    """Semanas del mes con los eventos de cada día (un evento largo aparece en cada día que abarca)."""
    primer, ultimo = datetime.date(anio, mes, 1), datetime.date(anio, mes, pycal.monthrange(anio, mes)[1])
    limite_inf = timezone.make_aware(datetime.datetime.combine(primer - datetime.timedelta(days=7), datetime.time.min))
    limite_sup = timezone.make_aware(datetime.datetime.combine(ultimo + datetime.timedelta(days=8), datetime.time.min))
    eventos = Evento.objects.filter(inicio__lt=limite_sup, fin__gte=limite_inf).exclude(estatus=E.CANCELADO).prefetch_related("asignaciones")
    if tecnico_id:
        eventos = eventos.filter(asignaciones__tecnico_id=tecnico_id).distinct()
    eventos = list(eventos)
    semanas = []
    for semana in pycal.Calendar(firstweekday=0).monthdatescalendar(anio, mes):
        fila = []
        for fecha in semana:
            del_dia = [e for e in eventos if _dia(e.inicio) <= fecha <= _dia(e.fin)]
            fila.append({"fecha": fecha, "en_mes": fecha.month == mes, "eventos": del_dia})
        semanas.append(fila)
    return semanas
