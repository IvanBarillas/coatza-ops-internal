from django import forms

from .models import Direccion, Documento


class DocumentoForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = ["tipo", "direccion", "contraparte", "director", "asunto", "fecha", "folio"]
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, direcciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["direccion"].queryset = (
            direcciones if direcciones is not None else Direccion.objects.none()
        )
        for campo in self.fields.values():
            campo.widget.attrs.setdefault(
                "class", "w-full rounded-xl border border-gray-300 px-3 py-2 text-sm"
            )
