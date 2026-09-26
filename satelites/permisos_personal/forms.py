import datetime

from django import forms
from django.utils import timezone

from .integracion import nombre_de_usuario, sedes_del_core, usuarios_con_acceso
from .models import Configuracion, Empleado, RangoAntiguedad, Solicitud, Tipo

CLASE = "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-[14px] font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white"
FECHA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def _estilo(form, excluir=()):
    for nombre, campo in form.fields.items():
        if nombre not in excluir:
            campo.widget.attrs.setdefault("class", CLASE)


class SolicitudForm(forms.Form):
    tipo = forms.ChoiceField(label="¿Qué solicita?", choices=Solicitud.TipoSolicitud.choices)
    fecha_inicio = forms.DateField(label="Del", widget=FECHA)
    fecha_fin = forms.DateField(label="Al", required=False, widget=FECHA, help_text="Si es un solo día, déjelo vacío.")
    comentarios = forms.CharField(label="Comentarios", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, empleado, **kwargs):
        super().__init__(*args, **kwargs)
        opciones = [(v, n) for v, n in Solicitud.TipoSolicitud.choices if v != "economico" or empleado.es_sindicalizado]
        self.fields["tipo"].choices = opciones
        _estilo(self)

    def clean(self):
        datos = super().clean()
        if datos.get("fecha_inicio") and not datos.get("fecha_fin"):
            datos["fecha_fin"] = datos["fecha_inicio"]
        return datos


class EmpleadoForm(forms.Form):
    usuario = forms.ModelChoiceField(label="Usuario", queryset=None)
    tipo = forms.ChoiceField(label="Tipo de personal", choices=Tipo.choices)
    fecha_ingreso = forms.DateField(label="Fecha de ingreso", widget=FECHA)
    sede = forms.ChoiceField(label="Sede", required=False)
    activo = forms.BooleanField(label="Activo", required=False, initial=True)

    def __init__(self, *args, empleado=None, app_slug="permisos_personal", **kwargs):
        if empleado is not None:
            kwargs.setdefault("initial", {
                "usuario": empleado.usuario_id, "tipo": empleado.tipo, "fecha_ingreso": empleado.fecha_ingreso,
                "sede": str(empleado.sede_uuid or ""), "activo": empleado.is_active,
            })
        super().__init__(*args, **kwargs)
        self.empleado = empleado
        ya = Empleado.objects.values("usuario_id")
        candidatos = usuarios_con_acceso(app_slug).exclude(pk__in=ya) if empleado is None else usuarios_con_acceso(app_slug).filter(pk=empleado.usuario_id)
        self.fields["usuario"].queryset = candidatos
        self.fields["usuario"].label_from_instance = lambda u: f"{nombre_de_usuario(u)} ({u.email})"
        if empleado is not None:
            self.fields["usuario"].disabled = True
        self._sedes = {str(pk): nombre for pk, nombre in sedes_del_core()}
        self.fields["sede"].choices = [("", "Sin sede")] + list(self._sedes.items())
        _estilo(self, excluir=("activo",))

    def clean_fecha_ingreso(self):
        fecha = self.cleaned_data["fecha_ingreso"]
        if fecha > timezone.localdate():
            raise forms.ValidationError("La fecha de ingreso no puede ser futura.")
        return fecha

    def clean_sede(self):
        valor = self.cleaned_data["sede"]
        if valor and valor not in self._sedes:
            raise forms.ValidationError("Elija una sede de la lista.")
        return valor


class AjusteForm(forms.Form):
    anio = forms.IntegerField(label="Año", min_value=2000, max_value=2100)
    periodo = forms.ChoiceField(label="Periodo", choices=((1, "1.er periodo (ene–jun)"), (2, "2.º periodo (jul–dic)")))
    dias = forms.IntegerField(label="Días de vacaciones", min_value=0, max_value=60)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilo(self)

    def clean_periodo(self):
        return int(self.cleaned_data["periodo"])


class ConfiguracionForm(forms.ModelForm):
    class Meta:
        model = Configuracion
        fields = ["dias_economicos_p1", "dias_economicos_p2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.update({"min": 0, "max": 30})
        _estilo(self)


class RangoForm(forms.ModelForm):
    class Meta:
        model = RangoAntiguedad
        fields = ["tipo", "desde_anios", "dias_p1", "dias_p2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilo(self)

    def validate_unique(self):
        """La fila (tipo, años) se sustituye si ya existe: lo resuelve la vista."""

    def validate_constraints(self):
        """Ídem."""


class UmbralForm(forms.Form):
    sede = forms.CharField()
    minimo = forms.IntegerField(min_value=0, max_value=500)


class MotivoForm(forms.Form):
    motivo = forms.CharField(label="Motivo", max_length=300)
