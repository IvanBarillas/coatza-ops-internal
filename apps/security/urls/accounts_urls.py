# apps/security/urls/accounts_urls.py (o donde manejes tus rutas de accounts)
from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from apps.security.views.mfa_views import mfa_setup_view, mfa_verify_view, mfa_replace_view
from apps.security.forms.identity_forms import ActiveIdentityAuthenticationForm
from apps.security.views.identity_views import IdentityPasswordChangeView, email_verification_view, email_confirm_view, email_change_view, email_change_confirm_view, account_security_view

from apps.security.views.accounts_views import (
    accounts_analytics_view, funcionario_list_view, funcionario_detail_view,
    funcionario_create_view, funcionario_editar_view, funcionario_cambiar_password_view,funcionario_soft_delete_view, funcionario_toggle_status_view,
    funcionario_sub_identidad_view,
    )


from apps.security.views.session_views import sessions_view

from apps.security.views.sudo_views import sudo_view

urls_accounts = [
    path('account/sudo/', sudo_view, name='sudo'),
    path('account/sessions/', sessions_view, name='sessions'),
    path('account/security/', account_security_view, name='account_security'),
    path('email/verify/', email_verification_view, name='email_verify'),
    path('email/confirm/<str:token>/', email_confirm_view, name='email_confirm'),
    path('email/change/', email_change_view, name='email_change'),
    path('email/change/confirm/<str:token>/', email_change_confirm_view, name='email_change_confirm'),
    path('mfa/replace/', mfa_replace_view, name='mfa_replace'),
    path('mfa/setup/', mfa_setup_view, name='mfa_setup'),
    path('mfa/verify/', mfa_verify_view, name='mfa_verify'),
    path('password/change/', IdentityPasswordChangeView.as_view(), name='password_change'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html', authentication_form=ActiveIdentityAuthenticationForm, redirect_authenticated_user=True), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='accounts:login'), name='logout'),
    path('acceso-denegado/', TemplateView.as_view(template_name='errors/403.html'), name='access_denied'),

    path('analytics/', accounts_analytics_view, name='analytics'),

    path('funcionarios/lista/', funcionario_list_view, name='funcionario_list'),
    path('funcionarios/detalle/<uuid:pk>/', funcionario_detail_view, name='funcionario_detail'),

    path('funcionarios/nuevo/', funcionario_create_view, name='funcionario_create'),
    path('funcionarios/editar/<uuid:pk>/', funcionario_editar_view, name='funcionario_update'),
    path('funcionarios/password/<uuid:pk>/', funcionario_cambiar_password_view, name='funcionario_password'),
    path('funcionarios/baja/<uuid:pk>/', funcionario_soft_delete_view, name='funcionario_delete'),
    path('funcionarios/estado/<uuid:pk>/', funcionario_toggle_status_view, name='funcionario_toggle_status'),

    path('funcionarios/sub/identidad/<uuid:pk>/', funcionario_sub_identidad_view, name='funcionario_sub_identidad'),

]