# apps/shared/notifications/services.py
"""Punto de entrada único de Core para encolar notificaciones por correo.

Cualquier app (Core o satélite) que necesite enviar un correo debe llamar a
enqueue_email() en vez de construir su propio EmailMessage/send() — así toda
la plataforma comparte una sola cola (Django-Q2, broker ORM), un solo lugar
con reintentos configurados y una sola solución al problema de líneas largas
(ver apps.shared.notifications.tasks). No es un servicio de dominio: no sabe
qué es un ticket, una invitación o un recordatorio — solo sabe encolar un
correo ya redactado por quien lo llama.
"""
from django.db import transaction
from django_q.tasks import async_task

from apps.shared.notifications.tasks import send_email_task


def enqueue_email(*, subject, body, to, from_email=None, ascii_only=True):
    """Encola un correo para envío asíncrono.

    Usa transaction.on_commit(): si la transacción actual se revierte, el
    correo nunca se encola — evita avisar de algo que en realidad no pasó.
    Con Q_CLUSTER['sync']=True (default en desarrollo) la tarea corre en el
    mismo proceso al hacer commit, sin exigir un `manage.py qcluster`
    aparte; en producción siempre es asíncrona real.

    to: email o lista de emails destino.
    """
    destinatarios = [to] if isinstance(to, str) else list(to)

    transaction.on_commit(lambda: async_task(
        send_email_task,
        subject=subject,
        body=body,
        to=destinatarios,
        from_email=from_email,
        ascii_only=ascii_only,
    ))
