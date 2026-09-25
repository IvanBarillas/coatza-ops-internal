import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from ..forms import _agregar_contraparte, _resolver_contraparte
from ..models import Bien, Gestor
from .services import exigir_motivo_de_estado

CLASE = "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-xs font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white"


class BienForm(forms.ModelForm):
    class Meta:
        model = Bien
        fields = ["direccion", "nombre", "marca_modelo", "identificador", "folio_inventario", "descripcion", "estado"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 2})}

    motivo = forms.CharField(
        label="Motivo del cambio de estado", required=False, max_length=300,
        help_text="Obligatorio para pasar a reparación o baja; opcional al volver a disponible.",
    )

    def __init__(self, *args, direcciones, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["direccion"].queryset = direcciones
        if not self.instance._state.adding:
            self.fields["direccion"].disabled = True
        self.mostrar_direccion = direcciones.count() > 1 and self.instance._state.adding
        if not self.mostrar_direccion:
            self.fields["direccion"].widget = forms.HiddenInput()
            if self.instance._state.adding and direcciones.count() == 1:
                self.fields["direccion"].initial = direcciones.first().pk
        self.fields["folio_inventario"].help_text = "Opcional. Si lo tiene, no puede repetirse en la dirección."
        for nombre, campo in self.fields.items():
            if nombre != "direccion":
                campo.widget.attrs.setdefault("class", CLASE)

    def validate_unique(self):
        """La unicidad del folio de inventario se valida en clean() con un mensaje claro."""

    def validate_constraints(self):
        """Ídem."""

    def clean(self):
        datos = super().clean()
        direccion = datos.get("direccion") or getattr(self.instance, "direccion", None)
        folio = (datos.get("folio_inventario") or "").strip()
        datos["folio_inventario"] = folio
        if direccion and folio and Bien.objects.filter(direccion=direccion, folio_inventario=folio).exclude(pk=self.instance.pk).exists():
            self.add_error("folio_inventario", "Ya existe un bien con ese folio de inventario en la dirección.")
        if not self.instance._state.adding:
            if datos.get("estado") != Bien.Estado.DISPONIBLE and self.instance.asignaciones.filter(abierto=True).exists():
                self.add_error("estado", "El bien está prestado: registre primero la devolución del vale.")
            try:
                exigir_motivo_de_estado(self.initial.get("estado"), datos.get("estado"), datos.get("motivo"))
            except ValidationError as error:
                self.add_error("motivo", error)
        return datos


class ValeForm(forms.Form):
    direccion = forms.ModelChoiceField(label="Dirección que presta", queryset=None)
    fecha_entrega = forms.DateField(label="Fecha de entrega", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    fecha_limite = forms.DateField(label="Devolución límite", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    contraparte = forms.CharField(label="Nombre si es otra / externa", max_length=200, required=False)
    gestor = forms.ModelChoiceField(label="Gestor (quien lo lleva)", queryset=None, required=False, empty_label="Sin asignar")
    bienes = forms.ModelMultipleChoiceField(label="Bienes que se prestan", queryset=None, widget=forms.CheckboxSelectMultiple)
    observaciones = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, direcciones, bienes, gestores, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["direccion"].queryset = direcciones
        self.mostrar_direccion = direcciones.count() != 1
        if not self.mostrar_direccion:
            self.fields["direccion"].initial = direcciones.first().pk
            self.fields["direccion"].widget = forms.HiddenInput()
        self.fields["bienes"].queryset = bienes
        self.fields["gestor"].queryset = gestores
        self.fields["fecha_entrega"].initial = timezone.localdate()
        self.fields["fecha_limite"].initial = timezone.localdate() + datetime.timedelta(days=7)
        _agregar_contraparte(self, "Dirección que recibe")
        self.fields["contraparte_dependencia"].choices = [
            ("", "Otra / externa (escribir nombre)")
        ] + self.fields["contraparte_dependencia"].choices[1:]
        for nombre, campo in self.fields.items():
            if nombre not in ("direccion", "bienes"):
                campo.widget.attrs.setdefault("class", CLASE)

    def clean(self):
        datos = super().clean()
        direccion = datos.get("direccion")
        _resolver_contraparte(self, datos, getattr(direccion, "dependencia_uuid", None))
        if direccion:
            gestor = datos.get("gestor")
            if gestor and gestor.direccion_id != direccion.pk:
                self.add_error("gestor", "El gestor no pertenece a la dirección.")
            if any(b.direccion_id != direccion.pk for b in datos.get("bienes", [])):
                self.add_error("bienes", "Hay bienes que no pertenecen a la dirección elegida.")
        entrega, limite = datos.get("fecha_entrega"), datos.get("fecha_limite")
        if entrega and limite and limite < entrega:
            self.add_error("fecha_limite", "No puede ser anterior a la entrega.")
        return datos


class DevolucionForm(forms.Form):
    fecha = forms.DateField(label="Fecha de devolución", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    observaciones = forms.CharField(label="Observaciones (estado en que regresa)", required=False, max_length=500)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", CLASE)


class ValeEdicionForm(forms.Form):
    fecha_entrega = forms.DateField(label="Fecha de entrega", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    fecha_limite = forms.DateField(label="Devolución límite", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    contraparte = forms.CharField(label="Nombre si es otra / externa", max_length=200, required=False)
    observaciones = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    motivo = forms.CharField(
        label="Motivo de la corrección", required=False, max_length=300,
        help_text="Obligatorio si el vale ya se firmó o entregó.",
    )

    def __init__(self, *args, prestamo, **kwargs):
        documento = prestamo.documento
        kwargs.setdefault("initial", {
            "fecha_entrega": prestamo.fecha_entrega, "fecha_limite": prestamo.fecha_limite,
            "observaciones": prestamo.observaciones,
            "contraparte_dependencia": str(documento.contraparte_dependencia_uuid or ""),
            "contraparte": "" if documento.contraparte_dependencia_uuid else documento.contraparte,
        })
        super().__init__(*args, **kwargs)
        _agregar_contraparte(self, "Dirección que recibe")
        self.fields["contraparte_dependencia"].choices = [
            ("", "Otra / externa (escribir nombre)")
        ] + self.fields["contraparte_dependencia"].choices[1:]
        self.propia = documento.direccion.dependencia_uuid
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", CLASE)

    def clean(self):
        datos = super().clean()
        _resolver_contraparte(self, datos, self.propia)
        return datos
