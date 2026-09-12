import time

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from django_otp import verify_token
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.security.middleware.sessions import auth_digest, client_ip
from apps.security.middleware.sudo import SUDO_KEY
from apps.security.models import SecurityAuditLog


@login_required
@never_cache
@sensitive_post_parameters('password', 'token')
@require_http_methods(['GET', 'POST'])
def sudo_view(request):
    device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    if settings.AXENTRA_REQUIRE_ADMIN_MFA and device is None:
        return redirect('accounts:mfa_setup')
    error = ''
    if request.method == 'POST':
        request.session.pop(SUDO_KEY, None)
        user = authenticate(request, username=request.user.email, password=request.POST.get('password', ''))
        valid = user is not None and user.pk == request.user.pk and user.password == request.user.password
        if valid and device:
            valid = verify_token(user, device.persistent_id, request.POST.get('token', '')) is not None
        if valid:
            request.session.cycle_key()
            request.session[SUDO_KEY] = {
                'at': time.time(), 'auth': auth_digest(user),
                'device': request.session.get('otp_device_id'),
            }
            SecurityAuditLog.objects.create(
                operator_user=user, target_user=user, app_namespace='accounts',
                module_component='sudo', action_type='ACCESS', action_name='Reautenticación administrativa',
                target_scope='Sesión propia: cinco minutos', ip_address=client_ip(request) or '127.0.0.1',
            )
            return redirect(request.session.pop('axentra_sudo_return', None) or 'accounts:account_security')
        error = 'No se pudo verificar. Revisa las credenciales o espera si hay un bloqueo temporal.'
    return render(request, 'registration/sudo.html', {'title': 'Confirmar identidad', 'needs_token': bool(device), 'error': error})
