from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ValidationError


class ActiveIdentityAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_deleted:
            raise ValidationError('Esta cuenta no está disponible.', code='inactive')


class IdentityPasswordChangeForm(PasswordChangeForm):
    def clean_new_password1(self):
        value = self.cleaned_data['new_password1']
        if self.user.check_password(value):
            raise ValidationError('La nueva contraseña debe ser diferente de la actual.')
        return value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'w-full rounded-lg border border-gray-300 p-3'
