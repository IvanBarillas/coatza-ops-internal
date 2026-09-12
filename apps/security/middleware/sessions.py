import hashlib
import ipaddress
from uuid import UUID

from django.contrib.auth import HASH_SESSION_KEY, logout
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from apps.security.models.sessions import AccountSession

SESSION_ID = 'axentra_account_session'


def auth_digest(user):
    return hashlib.sha256(user.get_session_auth_hash().encode()).hexdigest()


def client_ip(request):
    # No aceptar X-Forwarded-For de clientes sin una política de proxy confiable.
    try:
        return str(ipaddress.ip_address(request.META.get('REMOTE_ADDR', '')))
    except ValueError:
        return None


class AccountSessionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.account_session = None
        if not request.user.is_authenticated:
            return
        identifier = request.session.get(SESSION_ID)
        if identifier:
            try:
                identifier = UUID(str(identifier))
            except ValueError:
                identifier = None
            record = AccountSession.objects.filter(pk=identifier, user=request.user).first()
            if record is None or record.revoked_at is not None or record.auth_digest != auth_digest(request.user):
                logout(request)
                url = reverse('accounts:login')
                if request.headers.get('HX-Request', '').lower() == 'true':
                    return HttpResponse(headers={'HX-Redirect': url, 'Cache-Control': 'no-store'})
                return redirect(url)
            request.account_session = record
        else:
            # Sesiones anteriores al despliegue se incorporan en su siguiente acceso.
            self.register(request)

    def register(self, request):
        record = AccountSession.objects.create(
            user=request.user, auth_digest=auth_digest(request.user),
            last_seen_at=timezone.now(), expires_at=request.session.get_expiry_date(),
            ip_address=client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        )
        request.session[SESSION_ID] = str(record.pk)
        request.account_session = record

    def process_response(self, request, response):
        record = getattr(request, 'account_session', None)
        if response.status_code >= 500:
            return response
        if not request.user.is_authenticated:
            if record:
                AccountSession.objects.filter(pk=record.pk, revoked_at=None).update(revoked_at=timezone.now())
            return response
        if not record:
            self.register(request)
            return response
        updates = {}
        now = timezone.now()
        if (now - record.last_seen_at).total_seconds() >= 60:
            updates.update(last_seen_at=now, ip_address=client_ip(request))
        if request.session.modified:
            updates.update(expires_at=request.session.get_expiry_date(), auth_digest=hashlib.sha256(request.session[HASH_SESSION_KEY].encode()).hexdigest())
        if updates:
            # Una petición en vuelo nunca puede deshacer una revocación.
            AccountSession.objects.filter(pk=record.pk, revoked_at=None).update(**updates)
        return response
