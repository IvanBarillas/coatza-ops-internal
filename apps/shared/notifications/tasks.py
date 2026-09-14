# apps/shared/notifications/tasks.py
"""Tareas de Django-Q2 para envío asíncrono de correo (broker ORM, sin Redis).

No llamar send_email_task() directo desde una vista — usar
apps.shared.notifications.services.enqueue_email(), que además espera a que
la transacción actual confirme antes de encolar.
"""
import email.policy
import logging

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)

# Python's email.policy.default envuelve cualquier línea del cuerpo que pase
# de 78 caracteres (RFC 2822 §2.1.1, recomendación de visualización, no un
# límite real) insertando saltos "=\n" vía quoted-printable — rompe a la
# mitad cualquier URL firmada larga que caiga ahí (confirmación de correo,
# restablecimiento de contraseña, invitaciones...). Ocurre incluso con el
# backend SMTP real en producción (Django usa email.policy.SMTP ahí, mismo
# max_line_length=78); un cliente de correo real reconstruye el enlace sin
# problema al copiarlo, pero leer el .eml crudo (backend filebased/console
# de desarrollo) lo deja roto. 998 es el límite duro real de RFC 5322
# §2.1.1, así que subir a ese valor sigue siendo válido para cualquier
# transporte SMTP.
_WIDE_LINE_POLICY = email.policy.default.clone(max_line_length=998)


class SingleLineEmailMessage(EmailMessage):
    """EmailMessage que no envuelve líneas largas del cuerpo (ver _WIDE_LINE_POLICY)."""

    def message(self, *, policy=None):
        return super().message(policy=policy or _WIDE_LINE_POLICY)


def send_email_task(*, subject, body, to, from_email=None, ascii_only=True):
    """Tarea encolada por Django-Q2.

    ascii_only=True (default): fuerza charset us-ascii. Con utf-8, Python
    cambia a base64 (ilegible en crudo) en vez de 7bit al ampliar
    max_line_length, porque asume que puede haber bytes no ASCII — solo
    usar ascii_only=False si el cuerpo de verdad necesita acentos/emoji.

    Deja que la excepción se propague: Django-Q2 solo reintenta
    (Q_CLUSTER['retry']/['max_attempts']) las tareas que fallan; si aquí se
    silenciara, el envío fallido se marcaría como éxito.
    """
    mensaje = SingleLineEmailMessage(
        subject, body, from_email or settings.DEFAULT_FROM_EMAIL, list(to),
    )
    if ascii_only:
        mensaje.encoding = 'us-ascii'
    try:
        mensaje.send(fail_silently=False)
    except Exception:
        logger.exception("No se pudo enviar el correo a %s (asunto: %s)", to, subject)
        raise
