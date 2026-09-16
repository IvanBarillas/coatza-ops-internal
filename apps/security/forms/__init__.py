# apps/security/forms/__init__.py

from .security_forms import TenantConfigForm, PrivacidadCookiesForm
from .organigrama_forms import SedeForm, DependenciaForm, AreaOperativaForm
from .accounts_forms import (
    CustomUserCreationForm, CustomUserChangeForm,
    StaffUserCreationForm, StaffUserProfileForm,
    StaffUserChangeForm, StaffUserProfileChangeForm,
    AdminPasswordChangeForm
)

__all__ = [
    'TenantConfigForm', 'PrivacidadCookiesForm',
    'SedeForm', 'DependenciaForm', 'AreaOperativaForm',
    'CustomUserCreationForm', 'CustomUserChangeForm',
    'StaffUserCreationForm', 'StaffUserProfileForm',
    'StaffUserChangeForm', 'StaffUserProfileChangeForm',
    'AdminPasswordChangeForm'
]