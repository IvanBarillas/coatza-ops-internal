from django import forms

import uuid

from .integracion import dependencias_del_core, usuarios_con_acceso
from .models import ClaseDocumento, Direccion, Documento, Gestor, Nomenclatura


def _agregar_contraparte(form, etiqueta):
    opciones = dependencias_del_core()
    form.fields["contraparte_dependencia"] = forms.ChoiceField(
        label=etiqueta, required=False,
        choices=[("", "Otra / externa (escribir nombre)")] + [(str(pk), nombre) for pk, nombre in opciones],
    )
    form.fields["contraparte"].required = False
    form.fields["contraparte"].label = "Nombre si es otra / externa"
    form._dependencias = {str(pk): nombre for pk, nombre in opciones}


def _resolver_contraparte(form, datos, propia_uuid=None):
    elegido = datos.get("contraparte_dependencia")
    if elegido:
        if propia_uuid and elegido == str(propia_uuid):
            form.add_error("contraparte_dependencia", "No puede ser la propia dirección.")
            return
        datos["contraparte"] = form._dependencias.get(elegido, "")
        datos["contraparte_dependencia_uuid"] = uuid.UUID(elegido)
    else:
        datos["contraparte_dependencia_uuid"] = None
        if not (datos.get("contraparte") or "").strip():
            form.add_error("contraparte", "Elija una dirección o escriba el nombre.")


class DocumentoForm(forms.ModelForm):
    def clean(self):
        datos = super().clean()
        _resolver_contraparte(self, datos, getattr(datos.get("direccion"), "dependencia_uuid", None))
        gestor, direccion, sentido = datos.get("gestor"), datos.get("direccion"), datos.get("sentido")
        if gestor and sentido == "recibido":
            self.add_error("gestor", "Solo los documentos enviados llevan gestor.")
        elif gestor and direccion and gestor.direccion_id != direccion.pk:
            self.add_error("gestor", "El gestor no pertenece a la dirección elegida.")
        return datos

    class Meta:
        model = Documento
        fields = ["sentido", "clase", "direccion", "fecha", "contraparte", "director_nombre", "gestor", "folio", "asunto"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "sentido": forms.Select(attrs={"x-model": "sentido"}),
        }
        labels = {"director_nombre": "Director", "direccion": "Dirección que registra"}

    def __init__(self, *args, direcciones=None, gestores=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["direccion"].queryset = (
            direcciones if direcciones is not None else Direccion.objects.none()
        )
        propias = list(self.fields["direccion"].queryset[:2])
        self.mostrar_direccion = len(propias) != 1
        if not self.mostrar_direccion:
            self.fields["direccion"].initial = propias[0].pk
            self.fields["direccion"].widget = forms.HiddenInput()
        self.fields["sentido"].initial = Documento.Sentido.ENVIADO
        _agregar_contraparte(self, "Dirección destinataria / remitente")
        self.fields["gestor"].queryset = gestores if gestores is not None else Gestor.objects.none()
        self.fields["gestor"].required = False
        self.fields["gestor"].empty_label = "Sin asignar"
        self.fields["gestor"].help_text = "Quien llevará el oficio a la dependencia (solo enviados)."
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
    gestor = forms.ChoiceField(label="Gestor", required=False)
    tab = forms.CharField(required=False, widget=forms.HiddenInput)
    desde = forms.DateField(label="Desde", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    hasta = forms.DateField(label="Hasta", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    def __init__(self, *args, direcciones=None, gestores=(), **kwargs):
        super().__init__(*args, **kwargs)
        if direcciones is not None:
            self.fields["direccion"].queryset = direcciones
        self.fields["gestor"].choices = [("", "Todos los gestores"), ("sin", "Sin gestor")] + [
            (str(g.pk), g.nombre) for g in gestores
        ]
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


class DireccionForm(forms.ModelForm):
    dependencia = forms.ChoiceField(
        label="Dependencia del Core", required=False,
        help_text="Define quién ve los documentos de esta dirección. Sin vincular, solo los ve el administrador global.",
    )

    class Meta:
        model = Direccion
        fields = ["nombre", "is_active"]
        labels = {"is_active": "Activa"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dependencia"].choices = [("", "Sin vincular")] + [
            (str(pk), nombre) for pk, nombre in dependencias_del_core()
        ]
        if self.instance.dependencia_uuid:
            self.fields["dependencia"].initial = str(self.instance.dependencia_uuid)
        for nombre, campo in self.fields.items():
            if nombre != "is_active":
                campo.widget.attrs.setdefault("class", "w-full rounded-xl border border-gray-300 px-3 py-2 text-sm")

    def save(self, commit=True):
        valor = self.cleaned_data.get("dependencia")
        self.instance.dependencia_uuid = uuid.UUID(valor) if valor else None
        return super().save(commit)


class NomenclaturaForm(forms.ModelForm):
    class Meta:
        model = Nomenclatura
        fields = ["clase", "plantilla"]

    def __init__(self, *args, direccion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.direccion = direccion
        if not self.instance._state.adding:
            self.fields.pop("clase")
        elif direccion is not None:
            usadas = direccion.nomenclaturas.values_list("clase", flat=True)
            self.fields["clase"].choices = [(v, e) for v, e in ClaseDocumento.choices if v not in usadas]
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "w-full rounded-xl border border-gray-300 px-3 py-2 text-sm")

    def clean(self):
        datos = super().clean()
        clase = datos.get("clase")
        if self.direccion is not None and clase and self.direccion.nomenclaturas.filter(clase=clase).exists():
            self.add_error("clase", "Esa clase ya tiene nomenclatura en esta dirección.")
        return datos


class DocumentoEdicionForm(forms.Form):
    contraparte = forms.CharField(label="Nombre si es otra / externa", max_length=200, required=False)
    asunto = forms.CharField(label="Asunto", max_length=300)
    fecha = forms.DateField(
        label="Fecha del documento",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    folio = forms.CharField(label="Folio del remitente", max_length=80, required=False)
    motivo = forms.CharField(
        label="Motivo del cambio", required=False, max_length=300,
        help_text="Opcional; queda en el historial junto con los valores anterior y nuevo.",
    )

    gestor = forms.ModelChoiceField(label="Gestor", required=False, queryset=Gestor.objects.none(), empty_label="Sin asignar")

    def clean(self):
        datos = super().clean()
        _resolver_contraparte(self, datos, getattr(self.documento.direccion, "dependencia_uuid", None))
        return datos

    def __init__(self, *args, documento, **kwargs):
        super().__init__(*args, **kwargs)
        self.documento = documento
        _agregar_contraparte(
            self, "Dirección destinataria" if documento.sentido == "enviado" else "Dirección remitente"
        )
        if documento.contraparte_dependencia_uuid:
            self.initial.setdefault("contraparte_dependencia", str(documento.contraparte_dependencia_uuid))
        self.order_fields(["contraparte_dependencia", "contraparte", "asunto", "fecha", "folio", "gestor", "motivo"])
        if documento.sentido == "enviado":
            self.fields.pop("folio")
            self.fields["gestor"].queryset = Gestor.objects.filter(
                direccion=documento.direccion, is_active=True, is_deleted=False
            )
        else:
            self.fields.pop("gestor")
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "w-full rounded-xl border border-gray-300 px-3 py-2 text-sm")


class GestorForm(forms.ModelForm):
    class Meta:
        model = Gestor
        fields = ["nombre", "usuario"]

    def __init__(self, *args, direccion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.direccion = direccion or getattr(self.instance, "direccion", None)
        self.fields["usuario"].queryset = usuarios_con_acceso("seguimientos_oficios")
        self.fields["usuario"].required = False
        self.fields["nombre"].widget.attrs.setdefault(
            "class", "w-full rounded-xl border border-gray-300 px-3 py-2 text-sm"
        )

    def clean_nombre(self):
        nombre = " ".join(self.cleaned_data["nombre"].split())
        repetido = Gestor.objects.filter(direccion=self.direccion, nombre__iexact=nombre).exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Ya existe un gestor con ese nombre en esta dirección.")
        return nombre

    def clean_usuario(self):
        usuario = self.cleaned_data.get("usuario")
        if usuario and Gestor.objects.filter(direccion=self.direccion, usuario=usuario).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ese usuario ya está vinculado a otro gestor de esta dirección.")
        return usuario
