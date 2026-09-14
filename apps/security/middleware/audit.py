import uuid

from django.db import transaction
from django.http import HttpResponse

from apps.security.services.audit_context import current_audit


class AuditTransactionMiddleware:
    """Agrupa mutaciones HTTP y evidencia en la misma transacción de la BD default."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        context = {'id': uuid.uuid4(), 'failed': False}
        token = current_audit.set(context)
        request.audit_correlation_id = context['id']
        try:
            if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                with transaction.atomic():
                    response = self.get_response(request)
                    if context['failed'] or response.status_code >= 500:
                        transaction.set_rollback(True)
                    if context['failed']:
                        response = HttpResponse(
                            'No se pudo guardar la evidencia. La operación se ha cancelado; vuelve a intentarlo.',
                            status=503, headers={'Cache-Control': 'no-store', 'Retry-After': '30'},
                        )
                        # No emitir cookies de una sesión cuyos cambios se revirtieron.
            else:
                response = self.get_response(request)
            response['X-Request-ID'] = str(context['id'])
            return response
        finally:
            current_audit.reset(token)
