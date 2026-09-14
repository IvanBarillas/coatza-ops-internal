"""Contexto por petición; nunca acepta identificadores de correlación del cliente."""
from contextvars import ContextVar

current_audit = ContextVar('axentra_audit_context', default=None)


class AuditWriteError(RuntimeError):
    pass


def mark_audit_failure():
    context = current_audit.get()
    if context is not None:
        context['failed'] = True


def redact_payload(value, depth=0):
    if depth > 12:
        return '[OMITIDO: profundidad]'
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = str(key).lower().replace('-', '_')
            secret = any(word in normalized for word in ('password', 'secret', 'token', 'cookie', 'authorization', 'private_key'))
            result[str(key)] = '[REDACTADO]' if secret else redact_payload(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_payload(item, depth + 1) for item in value]
    return value
