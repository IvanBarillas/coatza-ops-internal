import time
from functools import wraps
from urllib.parse import urlsplit

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import url_has_allowed_host_and_scheme

from apps.security.middleware.sessions import auth_digest

SUDO_KEY = 'axentra_sudo'
SUDO_SECONDS = 300


def sudo_is_fresh(request):
    proof = request.session.get(SUDO_KEY, {})
    if not isinstance(proof, dict):
        return False
    try:
        age = time.time() - float(proof['at'])
    except (KeyError, ValueError, TypeError):
        return False
    return (0 <= age < SUDO_SECONDS and proof.get('auth') == auth_digest(request.user)
            and proof.get('device') == request.session.get('otp_device_id'))


def sudo_challenge(request):
    # No guardar ni reproducir automáticamente el cuerpo de una mutación.
    referer = request.headers.get('Referer', '')
    if url_has_allowed_host_and_scheme(referer, {request.get_host()}, require_https=request.is_secure()):
        parsed = urlsplit(referer)
        destination = parsed.path + ('?' + parsed.query if parsed.query else '')
    else:
        destination = reverse('index_hub')
    request.session['axentra_sudo_return'] = destination
    url = reverse('accounts:sudo')
    if request.headers.get('HX-Request', '').lower() == 'true':
        return HttpResponse(headers={'HX-Redirect': url, 'Cache-Control': 'no-store'})
    return redirect(url)


def sudo_required(view):
    """Step-up para mutaciones de satélites. No sustituye su gate de permisos."""
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and not sudo_is_fresh(request):
            return sudo_challenge(request)
        return view(request, *args, **kwargs)
    return wrapped


class SudoMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated or request.method in {'GET', 'HEAD', 'OPTIONS'}:
            return
        match = request.resolver_match
        protected = (
            match.namespace in {'security', 'configuration', 'organigrama'}
            or (match.namespace == 'admin' and match.url_name not in {'login', 'logout'})
            or (match.namespace == 'accounts' and match.url_name.startswith('funcionario_'))
            or match.view_name == 'module_toggle'
        )
        if protected and not sudo_is_fresh(request):
            return sudo_challenge(request)
