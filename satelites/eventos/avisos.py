"""Correos a los técnicos cuando se les asigna, se les quita o cambia un evento. Todo pasa por la cola del Core (`enqueue_email`).

No se avisa a quien hizo el cambio ni a usuarios sin correo. Los datos ficticios no avisan (`avisar=False`).
"""
from django.urls import reverse
from django.utils import timezone

from .integracion import enqueue_email, nombre_de_usuario, url_base


def _fmt(momento):
    return timezone.localtime(momento).strftime("%d/%m/%Y %H:%M")


def _enlace(evento):
    base = url_base()
    return f"\nDetalle: {base}{reverse('eventos:evento_detalle', args=[evento.pk])}\n" if base else ""


def _ficha(evento):
    lineas = [f"Evento: {evento.nombre}", f"Lugar: {evento.lugar}", f"Cuándo: {_fmt(evento.inicio)} a {_fmt(evento.fin)}"]
    if evento.ticket:
        lineas.append(f"Ticket: {evento.ticket}")
    if evento.descripcion:
        lineas.append(f"Qué se cubre: {evento.descripcion}")
    return "\n".join(lineas)


def _enviar(tecnicos, asunto, cuerpo, *, actor=None):
    correos = sorted({t.email for t in tecnicos if getattr(t, "email", "") and t != actor})
    for correo in correos:
        enqueue_email(subject=asunto, body=cuerpo, to=correo, ascii_only=False)


def asignado(asignacion, *, actor=None):
    e = asignacion.evento
    cuerpo = (
        f"Se le asignó al evento «{e.nombre}».\n\n{_ficha(e)}\n"
        f"Su tramo: {_fmt(asignacion.desde)} a {_fmt(asignacion.hasta)}"
        + (f" ({asignacion.nota})" if asignacion.nota else "") + f"\nAsignó: {nombre_de_usuario(actor) or 'el sistema'}\n{_enlace(e)}"
    )
    _enviar([asignacion.tecnico], f"Evento asignado: {e.nombre}", cuerpo, actor=actor)


def quitado(asignacion, *, actor=None):
    e = asignacion.evento
    cuerpo = f"Se quitó su asignación (o un tramo) del evento «{e.nombre}».\n\n{_ficha(e)}\nTramo quitado: {_fmt(asignacion.desde)} a {_fmt(asignacion.hasta)}\n"
    _enviar([asignacion.tecnico], f"Asignación quitada: {e.nombre}", cuerpo, actor=actor)


def modificado(evento, cambios, *, actor=None):
    """Cambió lo que le importa al técnico (fecha, lugar…). `cambios` es la lista de campos que cambiaron."""
    tecnicos = [a.tecnico for a in evento.asignaciones.select_related("tecnico")]
    cuerpo = f"El evento «{evento.nombre}» cambió: {', '.join(cambios)}.\n\n{_ficha(evento)}\n{_enlace(evento)}"
    _enviar(tecnicos, f"Evento modificado: {evento.nombre}", cuerpo, actor=actor)


def cancelado(evento, motivo, *, actor=None):
    tecnicos = [a.tecnico for a in evento.asignaciones.select_related("tecnico")]
    cuerpo = f"El evento «{evento.nombre}» se canceló.\nMotivo: {motivo}\n\n{_ficha(evento)}\n"
    _enviar(tecnicos, f"Evento cancelado: {evento.nombre}", cuerpo, actor=actor)
