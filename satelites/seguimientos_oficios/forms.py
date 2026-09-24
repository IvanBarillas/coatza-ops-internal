from django import forms

from .models import Direccion, Documento


class DocumentoForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = ["sentido", "clase", "direccion", "fecha", "contraparte", "director_nombre", "folio", "asunto"]
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
        labels = {"director_nombre": "Director"}

    campos_anchos = ("contraparte", "asunto")

    def __init__(self, *args, direcciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["direccion"].queryset = (
            direcciones if direcciones is not None else Direccion.objects.none()
        )
        self.fields["director_nombre"].help_text = "Vacío = titular actual de la dirección."
        self.fields["folio"].help_text = "Solo recibidos. En enviados se genera según la nomenclatura de la clase."
        for campo in self.fields.values():
            campo.widget.attrs.setdefault(
                "class", "w-full rounded-xl border border-gray-300 px-3 py-2 text-sm"
            )


class EntregaForm(forms.Form):
    fecha_entrega = forms.DateField(
        label="Fecha de entrega", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    receptor = forms.CharField(label="Recibió la entrega", max_length=200)


class CancelacionForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo de la cancelación", min_length=10,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Ej. Error en el número de serie del equipo X.",
    )
