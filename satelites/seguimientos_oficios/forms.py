from django import forms

from .models import ClaseDocumento, Direccion, Documento


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


class AdjuntoForm(forms.Form):
    archivo = forms.FileField(label="Archivo PDF", widget=forms.ClearableFileInput(attrs={"accept": "application/pdf"}))


class FiltroDocumentosForm(forms.Form):
    q = forms.CharField(
        label="Buscar", required=False, max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Folio, asunto, remitente o texto del documento…", "type": "search"}),
    )
    sentido = forms.ChoiceField(label="Sentido", required=False, choices=[("", "Todos")] + Documento.Sentido.choices)
    clase = forms.ChoiceField(label="Clase", required=False, choices=[("", "Todas")] + ClaseDocumento.choices)
    estado = forms.ChoiceField(label="Estado", required=False, choices=[("", "Todos")] + Documento.Estado.choices)
    direccion = forms.ModelChoiceField(label="Dirección", required=False, queryset=Direccion.objects.none())
    desde = forms.DateField(label="Desde", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    hasta = forms.DateField(label="Hasta", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    def __init__(self, *args, direcciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        if direcciones is not None:
            self.fields["direccion"].queryset = direcciones
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "w-full rounded-xl border border-gray-300 px-3 py-2 text-sm")


class BandejaConfigForm(forms.Form):
    ruta_recibidos = forms.CharField(label="Carpeta de recibidos", required=False, max_length=255)
    ruta_evidencias = forms.CharField(label="Carpeta de evidencias", required=False, max_length=255)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.update({
                "class": "w-full rounded-xl border border-gray-300 px-3 py-2 text-sm",
                "placeholder": "innovacion/oficios",
            })

    def _validar(self, campo):
        from . import bandeja

        valor = self.cleaned_data.get(campo, "").strip()
        if not valor:
            return ""
        try:
            return bandeja.ruta_normalizada(bandeja.resolver(valor))
        except bandeja.BandejaError as error:
            raise forms.ValidationError(str(error)) from error

    def clean_ruta_recibidos(self):
        return self._validar("ruta_recibidos")

    def clean_ruta_evidencias(self):
        return self._validar("ruta_evidencias")
