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
import email.policy
import uuid
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.mail import EmailMessage
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.utils import timezone

# Python's email.policy.default envuelve cualquier línea del cuerpo que pase
# de 78 caracteres (RFC 2822 §2.1.1, recomendación de visualización, no un
# límite real) insertando saltos "=\n" vía quoted-printable — justo en medio
# de la URL firmada de este correo, que supera ese largo. Esto ocurre incluso
# en el backend SMTP real, no solo en desarrollo (Django usa email.policy.SMTP
# ahí, con el mismo max_line_length=78); un cliente de correo real reconstruye
# el enlace sin problema al copiarlo, pero leer el .eml crudo (backend
# filebased/console de desarrollo) lo deja roto. 998 es el límite duro real
# de RFC 5322 §2.1.1, así que subir a ese valor sigue siendo válido para
# cualquier transporte SMTP.
_WIDE_LINE_POLICY = email.policy.default.clone(max_line_length=998)


class _SingleLineEmailMessage(EmailMessage):
    """EmailMessage que no envuelve líneas largas del cuerpo (ver _WIDE_LINE_POLICY)."""
    def message(self, *, policy=None):
        return super().message(policy=policy or _WIDE_LINE_POLICY)


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
                try:
                    mensaje = _SingleLineEmailMessage(
                        'Confirma tu correo - Axentra OS',
                        f'Confirma tu correo desde tu sesion:\n{url}\nEl enlace vence en 30 minutos.',
                        settings.DEFAULT_FROM_EMAIL,
                        [user.email],
                    )
                    # us-ascii: el cuerpo es puro ASCII a propósito; con utf-8 Python
                    # cambia a base64 (ilegible en crudo) en vez de 7bit al ampliar
                    # max_line_length, porque asume que puede haber bytes no ASCII.
                    mensaje.encoding = 'us-ascii'
                    mensaje.send(fail_silently=False)
                except Exception:
                    error = 'No se pudo enviar el correo. Reintenta más tarde.'
                if not error:
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
@require_http_methods(['GET'])
def account_security_view(request):
    from django_otp.plugins.otp_totp.models import TOTPDevice
    return render(request, 'registration/account_security.html', {
        'title': 'Seguridad de mi cuenta',
        'has_totp': TOTPDevice.objects.filter(user=request.user, confirmed=True).exists(),
    })
