import json

from django.core.serializers.json import DjangoJSONEncoder


def snapshot(instance, fields):
    """Campos explícitos; nunca serializar automáticamente el expediente completo."""
    from apps.security.services.audit_context import redact_payload
    values = {field: getattr(instance, field) for field in fields}
    return json.loads(json.dumps(redact_payload(values), cls=DjangoJSONEncoder))
