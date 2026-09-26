from django import forms

from .integracion import nombre_de_usuario, usuarios_con_acceso
from .models import Evento, TramiteLinea

CLASE = "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-[14px] font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white"
FORMATO = "%Y-%m-%dT%H:%M"
FORMATOS = [FORMATO, "%Y-%m-%d %H:%M"]


def _momento(etiqueta, **extra):
    return forms.DateTimeField(label=etiqueta, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=FORMATO), input_formats=FORMATOS, **extra)


def _estilo(form):
    for campo in form.fields.values():
        campo.widget.attrs.setdefault("class", CLASE)


class EventoForm(forms.Form):
    nombre = forms.CharField(label="Evento", max_length=200)
    lugar = forms.CharField(label="Lugar", max_length=200)
    inicio = _momento("Inicio")
    fin = _momento("Fin")
    ticket = forms.CharField(label="Ticket (si nació de uno)", max_length=60, required=False)
    descripcion = forms.CharField(label="Qué se cubre", required=False, widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, evento=None, **kwargs):
        if evento is not None and "initial" not in kwargs:
            kwargs["initial"] = {
                "nombre": evento.nombre, "lugar": evento.lugar, "inicio": evento.inicio, "fin": evento.fin,
                "ticket": evento.ticket, "descripcion": evento.descripcion,
            }
        super().__init__(*args, **kwargs)
        for nombre in ("inicio", "fin"):
            valor = self.initial.get(nombre)
            if valor:
                from django.utils import timezone
                self.initial[nombre] = timezone.localtime(valor).strftime(FORMATO)
        _estilo(self)

    def clean(self):
        datos = super().clean()
        if datos.get("inicio") and datos.get("fin") and datos["fin"] <= datos["inicio"]:
            self.add_error("fin", "El fin debe ser posterior al inicio.")
        return datos


class NombreUsuario(forms.ModelChoiceField):
    def label_from_instance(self, usuario):
        return nombre_de_usuario(usuario)


class AsignarForm(forms.Form):
    tecnico = NombreUsuario(label="Técnico", queryset=None)
    desde = _momento("Desde", required=False)
    hasta = _momento("Hasta", required=False)
    nota = forms.CharField(label="Nota", max_length=200, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tecnico"].queryset = usuarios_con_acceso("eventos")
        _estilo(self)

    def clean(self):
        datos = super().clean()
        if datos.get("desde") and datos.get("hasta") and datos["hasta"] <= datos["desde"]:
            self.add_error("hasta", "Debe ser posterior al inicio del tramo.")
        return datos


class ValeForm(forms.Form):
    vale = forms.ChoiceField(label="Vale del sistema", required=False)
    referencia = forms.CharField(label="O escriba su número", max_length=80, required=False)
    nota = forms.CharField(label="Qué se lleva", max_length=200, required=False)

    def __init__(self, *args, opciones=(), **kwargs):
        """`opciones`: [(uuid, etiqueta)] de los vales que ofrece el satélite de préstamos (vacío si no está instalado)."""
        super().__init__(*args, **kwargs)
        self.fields["vale"].choices = [("", "— Elegir un vale —")] + list(opciones)
        _estilo(self)

    def clean(self):
        datos = super().clean()
        if not datos.get("vale") and not (datos.get("referencia") or "").strip() and not self.errors:
            raise forms.ValidationError("Elija un vale o escriba su número.")
        return datos


class TramiteForm(forms.Form):
    tipo = forms.ChoiceField(label="Trámite", choices=TramiteLinea.Tipo.choices)
    descripcion = forms.CharField(label="Descripción", max_length=250)
    referencia = forms.CharField(label="Línea o enlace (si ya existe)", max_length=120, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilo(self)


class TextoForm(forms.Form):
    texto = forms.CharField(label="Texto", widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilo(self)
