import base64
import secrets
import time

import segno
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from django_otp import login as otp_login, verify_token
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice


def _pending(request):
    if time.time() - request.session.get('mfa_setup_started', 0) > 600:
        return None
    return TOTPDevice.objects.filter(
        pk=request.session.get('mfa_setup_device'), user=request.user, confirmed=False,
    ).first()


@login_required
@never_cache
@sensitive_post_parameters('password', 'token')
@require_http_methods(['GET', 'POST'])
def mfa_setup_view(request):
    if TOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
        return redirect('index_hub' if request.user.is_verified() else 'accounts:mfa_verify')
    error = ''
    codes = None
    if request.method == 'POST':
        if request.POST.get('action') == 'start':
            if authenticate(request, username=request.user.email, password=request.POST.get('password', '')) is not None:
                with transaction.atomic():
                    get_user_model().objects.select_for_update().get(pk=request.user.pk)
                    if not TOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
                        # Reutilizar el dispositivo conserva su límite de intentos.
                        device, _ = TOTPDevice.objects.get_or_create(user=request.user, name='Axentra', confirmed=False)
                        request.session['mfa_setup_device'] = device.pk
                        request.session['mfa_setup_started'] = time.time()
                return redirect('accounts:mfa_setup')
            error = 'Contraseña incorrecta.'
        elif request.POST.get('action') == 'confirm':
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                device = _pending(request)
                if device is not None:
                    device = TOTPDevice.objects.select_for_update().get(pk=device.pk)
                if device is not None and device.verify_token(request.POST.get('token', '')):
                    device.confirmed = True
                    device.save(update_fields=['confirmed'])
                    recovery, _ = StaticDevice.objects.get_or_create(user=request.user, name='Axentra recovery', confirmed=True)
                    recovery.token_set.all().delete()
                    codes = [secrets.token_hex(8) for _ in range(10)]
                    StaticToken.objects.bulk_create([StaticToken(device=recovery, token=code) for code in codes])
                    request.session.pop('mfa_setup_device', None)
                    request.session.pop('mfa_setup_started', None)
                    request.session.cycle_key()
                    otp_login(request, device)
                else:
                    error = 'Código inválido, vencido o temporalmente bloqueado. Espera antes de reintentar.'
    device = _pending(request) if codes is None else None
    return render(request, 'registration/mfa.html', {
        'setup': True, 'error': error, 'recovery_codes': codes,
        'qr_svg': segno.make(device.config_url).svg_inline(scale=4) if device else None,
        'secret': base64.b32encode(device.bin_key).decode() if device else None,
    })


@login_required
@never_cache
@sensitive_post_parameters('token')
@require_http_methods(['GET', 'POST'])
def mfa_verify_view(request):
    if request.user.is_verified():
        return redirect('index_hub')
    device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    if device is None:
        return redirect('accounts:mfa_setup')
    error = ''
    if request.method == 'POST':
        if request.POST.get('recovery') == 'on':
            device = StaticDevice.objects.filter(user=request.user, confirmed=True, name='Axentra recovery').first()
        verified = verify_token(request.user, device.persistent_id, request.POST.get('token', '').strip()) if device else None
        if verified:
            request.session.cycle_key()
            otp_login(request, verified)
            return redirect('index_hub')
        error = 'Código inválido, ya utilizado o temporalmente bloqueado. Espera antes de reintentar.'
    return render(request, 'registration/mfa.html', {'error': error})


@login_required
@never_cache
@sensitive_post_parameters('password')
@require_http_methods(['GET', 'POST'])
def mfa_replace_view(request):
    if not request.user.is_verified():
        return redirect('accounts:mfa_verify')
    error = ''
    if request.method == 'POST':
        if authenticate(request, username=request.user.email, password=request.POST.get('password', '')) is not None:
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                TOTPDevice.objects.filter(user=request.user).delete()
                StaticDevice.objects.filter(user=request.user).delete()
                request.session.pop('otp_device_id', None)
                request.session.pop('mfa_setup_device', None)
                request.session.pop('mfa_setup_started', None)
                request.session.cycle_key()
            return redirect('accounts:mfa_setup')
        error = 'Contraseña incorrecta o verificación temporalmente bloqueada.'
    return render(request, 'registration/mfa.html', {'replace': True, 'setup': True, 'error': error})
