from decimal import Decimal

from django import forms
from django.utils import timezone

from .mapa import coordenadas_de_texto
from .models import Evidencia, Linea, normalizar_identificador

CLASE = "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-[14px] font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white"
FECHA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def _estilo(form, excluir=()):
    for nombre, campo in form.fields.items():
        if nombre not in excluir:
            campo.widget.attrs.setdefault("class", CLASE)


class LineaForm(forms.ModelForm):
    enlace_maps = forms.CharField(
        label="Enlace o coordenadas de Google Maps", required=False,
        help_text="Pegue el enlace largo de Google Maps o «19.1234, -94.5678» y se llenan la latitud y la longitud.",
    )

    class Meta:
        model = Linea
        fields = ["identificador", "sitio", "tipo", "velocidad", "municipio", "direccion", "latitud", "longitud", "notas", "is_active"]
        widgets = {"notas": forms.Textarea(attrs={"rows": 2})}
        labels = {"is_active": "Activa"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilo(self, excluir=("is_active",))
        self.fields["latitud"].required = False
        self.fields["longitud"].required = False

    def validate_unique(self):
        """La unicidad del número se valida en clean_identificador, con un mensaje claro."""

    def validate_constraints(self):
        """Ídem."""

    def clean_identificador(self):
        identificador = " ".join(self.cleaned_data["identificador"].split())
        repetida = Linea.objects.filter(identificador_normalizado=normalizar_identificador(identificador)).exclude(pk=self.instance.pk)
        if repetida.exists():
            raise forms.ValidationError("Ya existe una línea con ese número o circuito.")
        return identificador

    def clean(self):
        datos = super().clean()
        enlace = (datos.get("enlace_maps") or "").strip()
        if enlace:
            coordenadas = coordenadas_de_texto(enlace)
            if coordenadas is None:
                self.add_error("enlace_maps", "No se encontraron coordenadas. Pegue el enlace largo de Google Maps (no el corto) o «latitud, longitud».")
            else:
                datos["latitud"], datos["longitud"] = (Decimal(f"{c:.6f}") for c in coordenadas)
        if (datos.get("latitud") is None) != (datos.get("longitud") is None):
            self.add_error("longitud", "Capture latitud y longitud juntas, o ninguna.")
        for campo, limite in (("latitud", 90), ("longitud", 180)):
            valor = datos.get(campo)
            if valor is not None and abs(valor) > limite:
                self.add_error(campo, "Valor fuera de rango.")
        return datos


class ReporteForm(forms.Form):
    linea = forms.ModelChoiceField(label="Línea", queryset=Linea.objects.none(), widget=forms.HiddenInput)
    folio = forms.CharField(label="Folio de Telmex", max_length=40)
    levantado = forms.DateField(label="Fecha en que se levantó", widget=FECHA)
    detalle = forms.CharField(label="Detalle de la falla", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    responsable = forms.ModelChoiceField(
        label="Responsable de Innovación (da seguimiento)", queryset=None, required=False, empty_label="Sin asignar",
    )
    contacto_nombre = forms.CharField(label="Contacto en sitio (nombre)", max_length=150, required=False)
    contacto_telefono = forms.CharField(label="Teléfono del contacto", max_length=30, required=False)

    def __init__(self, *args, lineas, responsables, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["linea"].queryset = lineas
        self.fields["responsable"].queryset = responsables
        self.fields["responsable"].label_from_instance = lambda u: getattr(u, "full_name", "") or u.email
        self.fields["levantado"].initial = timezone.localdate()
        self.fields["contacto_nombre"].help_text = "A quien Telmex le marcará para validar. Si es el responsable, puede dejarse vacío."
        _estilo(self, excluir=("linea",))


class ReporteEdicionForm(forms.Form):
    folio = forms.CharField(label="Folio de Telmex", max_length=40)
    levantado = forms.DateField(label="Fecha en que se levantó", widget=FECHA)
    detalle = forms.CharField(label="Detalle de la falla", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    contacto_nombre = forms.CharField(label="Contacto en sitio (nombre)", max_length=150)
    contacto_telefono = forms.CharField(label="Teléfono del contacto", max_length=30)
    motivo = forms.CharField(label="Motivo de la corrección", required=False, max_length=300)

    def __init__(self, *args, reporte, **kwargs):
        kwargs.setdefault("initial", {c: getattr(reporte, c) for c in ("folio", "levantado", "detalle", "contacto_nombre", "contacto_telefono")})
        super().__init__(*args, **kwargs)
        _estilo(self)


class ComentarioForm(forms.Form):
    texto = forms.CharField(label="Comentario", widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Qué pasó en la visita, qué falta, quién quedó de ir…"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilo(self)


class EvidenciaForm(forms.Form):
    # Sin `capture`: en el celular ofrece la cámara y también la galería (p. ej. una captura de la prueba de velocidad).
    archivo = forms.FileField(label="Foto o captura", widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp,application/pdf"}))
    tipo = forms.ChoiceField(label="Tipo", choices=Evidencia.Tipo.choices, initial=Evidencia.Tipo.FOTO)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilo(self, excluir=("archivo",))
        self.fields["tipo"].widget.attrs["class"] = CLASE.replace("w-full", "w-full sm:w-56 sm:shrink-0")


class AtenderForm(forms.Form):
    fecha = forms.DateField(label="Fecha de atención", required=False, widget=FECHA)
    comentario = forms.CharField(
        label="Comentario", required=False, max_length=500, widget=forms.TextInput(attrs={"placeholder": "Ej. Telmex ya validó el servicio"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilo(self)


class MotivoForm(forms.Form):
    motivo = forms.CharField(label="Motivo", max_length=300, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _estilo(self)
