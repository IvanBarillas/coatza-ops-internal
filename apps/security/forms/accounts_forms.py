# apps/security/forms/accounts_forms.py
from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import ReadOnlyPasswordHashField  
from apps.security.forms.base_styler import AxentraFormStylerMixin
from apps.security.models import UserProfile, AreaOperativa

User = get_user_model()

class InitialPasswordValidationMixin:
    def _post_clean(self):
        super()._post_clean()
        if self.cleaned_data.get('password'):
            try:
                validate_password(self.cleaned_data['password'], self.instance)
            except ValidationError as exc:
                self.add_error('password', exc)


class CustomUserCreationForm(InitialPasswordValidationMixin, forms.ModelForm):
    password = forms.CharField(label='Contraseña', widget=forms.PasswordInput, help_text='Ingrese una contraseña segura.')
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'password')
        
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        user.must_change_password = True
        if commit: user.save()
        return user


class CustomUserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(label="Contraseña", help_text="Las contraseñas se almacenan de forma encriptada.")
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'phone', 'password', 'is_active', 'is_staff', 'is_superuser')


class StaffUserCreationForm(InitialPasswordValidationMixin, AxentraFormStylerMixin, forms.ModelForm):
    password = forms.CharField(
        label='Contraseña Inicial',
        widget=forms.PasswordInput(attrs={'placeholder': '••••••••••••'}),
        help_text='Asigne una contraseña provisional segura.'
    )
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'phone')
        widgets = {
            'email': forms.EmailInput(attrs={'placeholder': 'ejemplo@ayuntamiento.gob.mx'}),
            'first_name': forms.TextInput(attrs={'placeholder': 'Nombres'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Apellidos'}),
            'phone': forms.TextInput(attrs={'placeholder': 'Teléfono Celular'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos_institucionales()


class StaffUserProfileForm(AxentraFormStylerMixin, forms.ModelForm):
    """Formulario de adscripción optimizado para mitigar consultas N+1 en la matriz."""
    class Meta:
        model = UserProfile
        fields = ('area', 'puesto', 'telefono_oficina')
        widgets = {
            'puesto': forms.TextInput(attrs={'placeholder': 'Ej: Jefa de Departamento'}),
            'telefono_oficina': forms.TextInput(attrs={'placeholder': 'Ej: Ext. 4500'}),
            'area': forms.Select(attrs={'id': 'id_area'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Sincronización Matricial mediante precarga RAM select_related
        self.fields['area'].queryset = AreaOperativa.objects.filter(
            is_active=True, is_deleted=False
        ).select_related('dependencia', 'sede_fisica').order_by('dependencia__nombre', 'nombre')
        
        self.fields['area'].empty_label = "--- Seleccione Oficina y Sede Territorial ---"
        
        # Formateador semántico Lambda para limpieza visual en la UX
        self.fields['area'].label_from_instance = lambda obj: f"🏢 {obj.dependencia.nombre.upper()} ➔ {obj.nombre.upper()} [📍 {obj.sede_fisica.nombre.upper()}]"
        self.fields['area'].required = True
        
        self.aplicar_estilos_institucionales()


class StaffUserChangeForm(AxentraFormStylerMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone')
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos_institucionales()


class StaffUserProfileChangeForm(AxentraFormStylerMixin, forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('area', 'puesto', 'telefono_oficina')
        widgets = {
            'puesto': forms.TextInput(attrs={'placeholder': 'Ej: Jefe de Departamento'}),
            'telefono_oficina': forms.TextInput(attrs={'placeholder': 'Ext. 4500'}),
            'area': forms.Select(attrs={'id': 'id_area'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['area'].queryset = AreaOperativa.objects.filter(
            is_active=True, is_deleted=False
        ).select_related('dependencia', 'sede_fisica').order_by('dependencia__nombre', 'nombre')
        
        self.fields['area'].empty_label = "--- Seleccione Nueva Adscripción Matriz ---"
        self.fields['area'].label_from_instance = lambda obj: f"🏢 {obj.dependencia.nombre.upper()} ➔ {obj.nombre.upper()} [📍 {obj.sede_fisica.nombre.upper()}]"
        
        self.aplicar_estilos_institucionales()


class AdminPasswordChangeForm(AxentraFormStylerMixin, forms.Form):
    password = forms.CharField(label="Nueva Contraseña", widget=forms.PasswordInput(attrs={'placeholder': '••••••••••••'}))
    confirm_password = forms.CharField(label="Confirmar Nueva Contraseña", widget=forms.PasswordInput(attrs={'placeholder': '••••••••••••'}))
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos_institucionales()
        
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password") != cleaned_data.get("confirm_password"):
            raise forms.ValidationError("Las contraseñas no coinciden.")
        return cleaned_data