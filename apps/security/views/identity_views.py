from django.contrib.auth.views import PasswordChangeView
from django.db import transaction
from django.urls import reverse_lazy

from apps.security.forms.identity_forms import IdentityPasswordChangeForm


class IdentityPasswordChangeView(PasswordChangeView):
    form_class = IdentityPasswordChangeForm
    template_name = 'registration/password_change.html'
    success_url = reverse_lazy('index_hub')

    def form_valid(self, form):
        with transaction.atomic():
            current = get_user_model().objects.select_for_update().get(pk=form.user.pk)
            if current.password != form.user.password or not current.is_active or current.is_deleted:
                form.add_error(None, 'Tu cuenta cambió durante la operación. Vuelve a iniciar sesión.')
                return self.form_invalid(form)
            form.user = current
            form.user.must_change_password = False
            # Django guarda el nuevo hash y renueva solo esta sesión.
            # Las otras sesiones pierden validez al contrastar el hash anterior.
            return super().form_valid(form)


# Acciones personales: middleware exige cambio inicial y MFA antes de ejecutarlas.
import uuid
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.shared.notifications.services import enqueue_email


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def email_verification_view(request):
    error = ''
    if request.method == 'POST' and not request.user.is_email_verified:
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            if user.email_verification_sent_at and (timezone.now() - user.email_verification_sent_at).total_seconds() < 60:
                error = 'Espera un minuto antes de solicitar otro enlace.'
            else:
                user.email_verification_nonce = uuid.uuid4()
                user.email_verification_sent_at = timezone.now()
                user.save(update_fields=['email_verification_nonce', 'email_verification_sent_at'])
                token = signing.dumps({'user': str(user.pk), 'email': user.email, 'nonce': str(user.email_verification_nonce)}, salt='axentra.verify-email')
                url = request.build_absolute_uri(reverse('accounts:email_confirm', args=[token]))
                # Se encola con transaction.on_commit (dentro de enqueue_email): si algo
                # de este bloque atómico se revierte después, el correo nunca se envía.
                # El envío real (y sus reintentos) los resuelve el worker de Django-Q2,
                # no este request — ver apps.shared.notifications.
                enqueue_email(
                    subject='Confirma tu correo - Axentra OS',
                    body=f'Confirma tu correo desde tu sesion:\n{url}\nEl enlace vence en 30 minutos.',
                    to=user.email,
                )
                messages.success(request, 'Enviamos un enlace de confirmación a tu correo.')
    return render(request, 'registration/identity_action.html', {'title': 'Verificar correo', 'error': error, 'verified': request.user.is_email_verified})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def email_confirm_view(request, token):
    valid = False
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        try:
            payload = signing.loads(token, salt='axentra.verify-email', max_age=1800)
            valid = payload == {'user': str(user.pk), 'email': user.email, 'nonce': str(user.email_verification_nonce)} and not user.is_email_verified
        except signing.BadSignature:
            pass
        if valid and request.method == 'POST':
            user.is_email_verified = True
            user.email_verification_nonce = uuid.uuid4()
            user.save(update_fields=['is_email_verified', 'email_verification_nonce'])
            messages.success(request, 'Correo confirmado.')
            return redirect('index_hub')
    return render(request, 'registration/identity_action.html', {'title': 'Confirmar correo', 'error': '' if valid else 'El enlace no es válido para esta cuenta o ya venció.', 'invalid': not valid}, status=200 if valid else 400)


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def email_change_view(request):
    """Solicita cambiar el correo de acceso. No lo cambia todavía.

    Guarda el destino en pending_email y manda el enlace de confirmación ahí
    — el correo real (User.email) solo se toca en email_change_confirm_view,
    cuando se prueba que el solicitante controla esa bandeja. También avisa
    al correo actual: si la sesión está comprometida, su dueño real se
    entera de la solicitud antes de que se consume el enlace.
    """
    error = ''
    if request.method == 'POST':
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            nuevo_correo = (request.POST.get('new_email') or '').strip().lower()
            if authenticate(request, username=user.email, password=request.POST.get('password', '')) is None:
                error = 'Contraseña incorrecta.'
            elif user.pending_email_requested_at and (timezone.now() - user.pending_email_requested_at).total_seconds() < 60:
                error = 'Espera un minuto antes de solicitar otro cambio.'
            elif not nuevo_correo or nuevo_correo == user.email:
                error = 'Ingresa un correo distinto al actual.'
            elif get_user_model().objects.filter(email=nuevo_correo).exclude(pk=user.pk).exists():
                error = 'Ese correo ya está en uso por otra cuenta.'
            else:
                user.pending_email = nuevo_correo
                user.pending_email_nonce = uuid.uuid4()
                user.pending_email_requested_at = timezone.now()
                user.save(update_fields=['pending_email', 'pending_email_nonce', 'pending_email_requested_at'])
                token = signing.dumps({'user': str(user.pk), 'new_email': nuevo_correo, 'nonce': str(user.pending_email_nonce)}, salt='axentra.change-email')
                url = request.build_absolute_uri(reverse('accounts:email_change_confirm', args=[token]))
                enqueue_email(
                    subject='Confirma tu nuevo correo - Axentra OS',
                    body=f'Confirma tu nuevo correo de acceso desde tu sesion:\n{url}\nEl enlace vence en 30 minutos.\nSi no solicitaste este cambio, ignora este mensaje.',
                    to=nuevo_correo,
                )
                enqueue_email(
                    subject='Solicitud de cambio de correo - Axentra OS',
                    body=(
                        f'Alguien con acceso a esta cuenta ({user.email}) solicito cambiar '
                        f'el correo de acceso a {nuevo_correo}.\nSi no fuiste tu, cambia tu '
                        'contrasena de inmediato y contacta al administrador de tu institucion.'
                    ),
                    to=user.email,
                )
                messages.success(request, 'Enviamos un enlace de confirmación a tu nuevo correo.')
    return render(request, 'registration/email_change.html', {'title': 'Cambiar correo', 'error': error, 'pending_email': request.user.pending_email})


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def email_change_confirm_view(request, token):
    valid = False
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        try:
            payload = signing.loads(token, salt='axentra.change-email', max_age=1800)
            valid = bool(user.pending_email) and payload == {
                'user': str(user.pk), 'new_email': user.pending_email, 'nonce': str(user.pending_email_nonce),
            }
        except signing.BadSignature:
            pass
        if valid and request.method == 'POST':
            nuevo_correo = user.pending_email
            if get_user_model().objects.filter(email=nuevo_correo).exclude(pk=user.pk).exists():
                valid = False
            else:
                user.email = nuevo_correo
                user.pending_email = ''
                user.pending_email_nonce = uuid.uuid4()
                user.pending_email_requested_at = None
                # El save() del modelo pone is_email_verified=False y avisa al
                # correo anterior de forma automática (ver User.save). Aquí sí
                # se probó la propiedad del nuevo correo — se restaura aparte,
                # en un segundo save() que ya no toca 'email' y por lo tanto no
                # vuelve a disparar ese reset.
                user.save()
                user.is_email_verified = True
                user.save(update_fields=['is_email_verified'])
                messages.success(request, 'Tu correo de acceso se actualizó.')
                return redirect('accounts:account_security')
    return render(request, 'registration/identity_action.html', {
        'title': 'Confirmar nuevo correo',
        'error': '' if valid else 'El enlace no es válido para esta cuenta o ya venció.',
        'invalid': not valid,
        'pending_email': request.user.pending_email,
    }, status=200 if valid else 400)


@login_required
@never_cache
@require_http_methods(['GET'])
def account_security_view(request):
    from django_otp.plugins.otp_totp.models import TOTPDevice
    return render(request, 'registration/account_security.html', {
        'title': 'Seguridad de mi cuenta',
        'has_totp': TOTPDevice.objects.filter(user=request.user, confirmed=True).exists(),
    })
