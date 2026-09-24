from django import forms

from .models import Direccion, Documento


class DocumentoForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = ["sentido", "clase", "direccion", "contraparte", "director_nombre", "asunto", "fecha", "folio"]
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
        labels = {"director_nombre": "Director"}

    def __init__(self, *args, direcciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["direccion"].queryset = (
            direcciones if direcciones is not None else Direccion.objects.none()
        )
        self.fields["director_nombre"].help_text = "Vacío = titular actual de la dirección."
        self.fields["folio"].help_text = "Solo recibidos. En enviados se genera solo (ej. IN-001/2026)."
        for campo in self.fields.values():
            campo.widget.attrs.setdefault(
                "class", "w-full rounded-xl border border-gray-300 px-3 py-2 text-sm"
            )
