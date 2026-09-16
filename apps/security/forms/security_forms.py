# apps/security/forms/security_forms.py
import re
from django import forms
from apps.security.forms.base_styler import AxentraFormStylerMixin
from apps.security.models import TenantConfig
from apps.security.models.infrastructure import Municipality


class ColorInput(forms.TextInput):
    """Input HTML5 nativo de selección de color (paleta institucional)."""

    input_type = "color"


class TenantConfigForm(AxentraFormStylerMixin, forms.ModelForm):
    """Formulario del Singleton de Identidad Corporativa."""

    class Meta:
        model = TenantConfig

        fields = [
            "app_name",
            "entidad_nombre",
            "siglas",
            "municipality",
            "direccion_oficial",
            "rfc",
            "logo_light",
            "primary_color",
            "secondary_color",
            "accent_color",
            "enable_whatsapp_support",
            "whatsapp_number",
            "whatsapp_default_message",
            "show_whatsapp_on_public_landing",
        ]

        widgets = {
            "app_name": forms.TextInput(
                attrs={
                    "placeholder": "Ej: Axentra OS",
                }
            ),
            "entidad_nombre": forms.TextInput(
                attrs={
                    "placeholder": "Ej: H. Ayuntamiento Constitucional de Coatzacoalcos",
                }
            ),
            "siglas": forms.TextInput(
                attrs={
                    "placeholder": "Ej: COATZA",
                }
            ),
            "municipality": forms.Select(),
            "direccion_oficial": forms.Textarea(
                attrs={
                    "placeholder": "Dirección legal completa...",
                    "rows": 2,
                }
            ),
            "rfc": forms.TextInput(
                attrs={
                    "placeholder": "Ej: MCO850101AAA",
                }
            ),
            "logo_light": forms.ClearableFileInput(
                attrs={
                    "class": (
                        "block w-full text-xs text-slate-500 "
                        "file:mr-4 file:py-2.5 file:px-4 file:rounded-xl file:border-0 "
                        "file:text-[10px] file:font-black file:uppercase file:tracking-widest "
                        "file:bg-slate-950 file:text-white hover:file:bg-slate-900 "
                        "file:transition-colors file:cursor-pointer"
                    )
                }
            ),
            "primary_color": ColorInput(),
            "secondary_color": ColorInput(),
            "accent_color": ColorInput(),
            "enable_whatsapp_support": forms.CheckboxInput(
                attrs={
                    "class": "peer sr-only",
                }
            ),
            "whatsapp_number": forms.TextInput(
                attrs={
                    "placeholder": "Ej: 5219211234567",
                    "inputmode": "numeric",
                }
            ),
            "whatsapp_default_message": forms.TextInput(
                attrs={
                    "placeholder": "Ej: Hola, necesito asistencia en el Portal Digital de Axentra OS.",
                    "maxlength": "255",
                }
            ),
            "show_whatsapp_on_public_landing": forms.CheckboxInput(
                attrs={
                    "class": "peer sr-only",
                }
            ),
        }

        labels = {
            "app_name": "Nombre comercial de la plataforma",
            "entidad_nombre": "Nombre oficial del ayuntamiento / institución",
            "siglas": "Siglas internas",
            "municipality": "Municipio oficial",
            "direccion_oficial": "Dirección legal de la sede central",
            "rfc": "Registro Federal de Contribuyentes",
            "logo_light": "Escudo / logotipo oficial",
            "primary_color": "Color primario",
            "secondary_color": "Color secundario",
            "accent_color": "Color de acento",
            "enable_whatsapp_support": "Soporte por WhatsApp",
            "whatsapp_number": "Número institucional de WhatsApp",
            "whatsapp_default_message": "Mensaje inicial de WhatsApp",
            "show_whatsapp_on_public_landing": "Mostrar en portada pública",
        }

        help_texts = {
            "municipality": "Municipio oficial asociado a esta instalación. Define el segmento [MUN] de folios patrimoniales. Ejemplo: 039 · COATZACOALCOS.",
            "primary_color": "Color primario de marca: chasis global, sidebar y botones principales.",
            "secondary_color": "Color secundario de apoyo para textos y superficies neutras de marca.",
            "accent_color": "Color de acento para resaltados, estados activos y detalles interactivos.",
            "enable_whatsapp_support": "Muestra u oculta el botón flotante de contacto por WhatsApp en la portada pública.",
            "whatsapp_number": "Código de país + número, solo dígitos (sin espacios, guiones ni símbolo +). Ejemplo: 5219211234567.",
            "whatsapp_default_message": "Texto precargado en la conversación de WhatsApp cuando el ciudadano abre el chat.",
            "show_whatsapp_on_public_landing": "Interruptor específico para la portada pública del Core; aplicaciones satélite pueden definir su propia condición al sobreescribir el bloque whatsapp_widget.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.fields.get("municipality"):
            self.fields["municipality"].queryset = (
                Municipality.objects
                .filter(
                    is_active=True,
                    is_deleted=False,
                )
                .order_by(
                    "state_code",
                    "code",
                    "name",
                )
            )
            self.fields["municipality"].required = False
            self.fields["municipality"].empty_label = "--- Seleccione municipio oficial ---"

        self.aplicar_estilos_institucionales()

    def clean_rfc(self):
        rfc_crudo = self.cleaned_data.get("rfc", "").strip().upper()

        if not rfc_crudo:
            return rfc_crudo

        patron_rfc = r"^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$"

        if not re.match(patron_rfc, rfc_crudo):
            raise forms.ValidationError(
                "⚠️ Estructura Inválida: El RFC ingresado no coincide con el formato oficial del SAT."
            )

        return rfc_crudo

    def clean_whatsapp_number(self):
        numero_crudo = self.cleaned_data.get("whatsapp_number", "").strip()

        if not numero_crudo:
            return numero_crudo

        solo_digitos = re.sub(r"\D", "", numero_crudo)

        if not solo_digitos:
            raise forms.ValidationError(
                "Ingrese un número de WhatsApp válido, con código de país (solo dígitos)."
            )

        return solo_digitos


class PrivacidadCookiesForm(AxentraFormStylerMixin, forms.ModelForm):
    """Formulario aparte del mismo Singleton (TenantConfig) — sección
    propia de Configuración en vez de una cuarta pestaña dentro de
    Identidad Institucional (ya tiene tres: Identidad y Marca,
    Integraciones y Canales, Datos Legales y Fiscales). Fuente única de
    verdad legal para toda la instalación — ver docs/apps/
    public-municipal-portal.md: cada satélite instalado por separado
    duplicaba su propio aviso de privacidad antes de esto."""

    class Meta:
        model = TenantConfig

        fields = [
            "aviso_privacidad",
            "politica_cookies",
        ]

        widgets = {
            "aviso_privacidad": forms.Textarea(
                attrs={
                    "placeholder": "Texto completo del aviso de privacidad...",
                    "rows": 10,
                }
            ),
            "politica_cookies": forms.Textarea(
                attrs={
                    "placeholder": "Texto completo de la política de cookies...",
                    "rows": 10,
                }
            ),
        }

        labels = {
            "aviso_privacidad": "Aviso de privacidad",
            "politica_cookies": "Política de cookies",
        }

        help_texts = {
            "aviso_privacidad": "Fuente única para todo el portal público y cualquier satélite instalado — no se duplica por app.",
            "politica_cookies": "Fuente única para todo el portal público y cualquier satélite instalado — no se duplica por app.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_estilos_institucionales()
