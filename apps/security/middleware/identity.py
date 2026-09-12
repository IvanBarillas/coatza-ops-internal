from django.conf import settings
from django.contrib.auth import logout
from django_otp.plugins.otp_totp.models import TOTPDevice
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


class IdentityLifecycleMiddleware(MiddlewareMixin):
    """Aplica bajas y cambio inicial a todas las vistas, incluido Admin y HTMX."""
    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        if not user.is_authenticated:
            return None
        target = None
        if not user.is_active or user.is_deleted:
            logout(request)
            target = 'accounts:login'
        else:
            view_name = request.resolver_match.view_name
            has_device = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
            required = has_device or (
                settings.AXENTRA_REQUIRE_ADMIN_MFA
                and (user.is_staff or user.is_manager or user.is_superuser)
            )
            if view_name == 'accounts:logout':
                return None
            # Un dispositivo ya inscrito se verifica antes de cambiar contraseña.
            if has_device and not user.is_verified():
                if view_name != 'accounts:mfa_verify':
                    target = 'accounts:mfa_verify'
            elif user.must_change_password:
                if view_name != 'accounts:password_change':
                    target = 'accounts:password_change'
            elif required and not user.is_verified():
                if view_name != 'accounts:mfa_setup':
                    target = 'accounts:mfa_setup'
            elif settings.AXENTRA_REQUIRE_VERIFIED_EMAIL and not user.is_email_verified:
                if view_name not in {'accounts:email_verify', 'accounts:email_confirm'}:
                    target = 'accounts:email_verify'
        if target is None:
            return None
        url = reverse(target)
        if request.headers.get('HX-Request', '').lower() == 'true':
            return HttpResponse(status=200, headers={'HX-Redirect': url, 'Cache-Control': 'no-store'})
        return redirect(url)
