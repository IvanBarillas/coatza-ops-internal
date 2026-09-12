import uuid

from django.contrib.auth import authenticate, get_user_model, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from apps.security.middleware.sessions import auth_digest
from apps.security.models import AccountSession, SecurityAuditLog


@login_required
@never_cache
@sensitive_post_parameters('password')
@require_http_methods(['GET', 'POST'])
def sessions_view(request):
    error = ''
    if request.method == 'POST':
        target = None
        if request.POST.get('action') != 'others':
            try:
                identifier = uuid.UUID(request.POST.get('session', ''))
            except ValueError:
                identifier = None
            target = get_object_or_404(AccountSession, pk=identifier, user=request.user)
        if authenticate(request, username=request.user.email, password=request.POST.get('password', '')) is None:
            error = 'Contraseña incorrecta o verificación temporalmente bloqueada.'
        else:
            with transaction.atomic():
                user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
                if user.password != request.user.password or not user.is_active or user.is_deleted:
                    logout(request)
                    return redirect('accounts:login')
                now = timezone.now()
                if target is None:
                    user.session_version = uuid.uuid4()
                    user.save(update_fields=['session_version'])
                    AccountSession.objects.filter(user=user, revoked_at=None).exclude(pk=request.account_session.pk).update(revoked_at=now)
                    update_session_auth_hash(request, user)
                    request.user = user
                    label = 'Revocación de otras sesiones'
                else:
                    AccountSession.objects.filter(pk=target.pk, user=user, revoked_at=None).update(revoked_at=now)
                    label = 'Revocación de sesión individual'
                SecurityAuditLog.objects.create(
                    operator_user=user, target_user=user, app_namespace='accounts',
                    module_component='sessions', action_type='RESET', action_name=label,
                    target_scope=str(target.pk) if target else 'Otras sesiones propias',
                )
            if target and target.pk == request.account_session.pk:
                logout(request)
                return redirect('accounts:login')
            return redirect('accounts:sessions')
    active = AccountSession.objects.filter(user=request.user, revoked_at=None, auth_digest=auth_digest(request.user), expires_at__gt=timezone.now())
    return render(request, 'registration/sessions.html', {
        'title': 'Mis sesiones', 'sessions': Paginator(active, 20).get_page(request.GET.get('page')),
        'current_session': request.account_session.pk, 'error': error,
    })
