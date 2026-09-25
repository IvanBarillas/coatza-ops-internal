from django import forms

import uuid

from django.db.models import Q

from .integracion import dependencias_del_core, usuarios_con_acceso
from .models import Categoria, ClaseDocumento, Direccion, Documento, Gestor, Nomenclatura


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
    def validate_unique(self):
        """La unicidad del folio la valida el servicio, con un mensaje claro."""

    def validate_constraints(self):
        """Ídem: evita el mensaje genérico de la restricción de folio único."""

    def clean(self):
        datos = super().clean()
        _resolver_contraparte(self, datos, getattr(datos.get("direccion"), "dependencia_uuid", None))
        gestor, direccion, sentido = datos.get("gestor"), datos.get("direccion"), datos.get("sentido")
        if gestor and sentido == "recibido":
            self.add_error("gestor", "Solo los documentos enviados llevan gestor.")
        elif gestor and direccion and gestor.direccion_id != direccion.pk:
            self.add_error("gestor", "El gestor no pertenece a la dirección elegida.")
        categoria = datos.get("categoria")
        if categoria and direccion and categoria.direccion_id != direccion.pk:
            self.add_error("categoria", "La categoría no pertenece a la dirección elegida.")
        if sentido == "enviado" and direccion and direccion.folio_manual and not (datos.get("folio") or "").strip():
            self.add_error("folio", "Escriba el folio del oficio.")
        return datos

    class Meta:
        model = Documento
        fields = ["sentido", "clase", "direccion", "fecha", "contraparte", "gestor", "categoria", "folio", "asunto"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "sentido": forms.Select(attrs={"x-model": "sentido"}),
        }
        labels = {"direccion": "Dirección que registra"}

    def __init__(self, *args, direcciones=None, gestores=None, categorias=None, puede_soporte=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not puede_soporte:
            # Diagnósticos y dictámenes solo los registra quien tiene el permiso de soporte técnico.
            reservadas = {ClaseDocumento.DIAGNOSTICO_TECNICO, ClaseDocumento.DICTAMEN_ALTA, ClaseDocumento.DICTAMEN_BAJA}
            self.fields["clase"].choices = [(v, e) for v, e in self.fields["clase"].choices if v not in reservadas]
        self.fields["categoria"].queryset = categorias if categorias is not None else Categoria.objects.none()
        self.fields["categoria"].required = False
        self.fields["categoria"].empty_label = "Sin categoría"
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
        self.fields["folio"].required = False
        self.fields["folio"].help_text = "Escríbelo tal como aparece en el oficio."
        self.hay_folio_manual = any(d.folio_manual for d in self.fields["direccion"].queryset)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault(
                "class", "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-xs font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white"
            )


class EntregaForm(forms.Form):
    fecha_entrega = forms.DateField(
        label="Fecha de entrega",
        widget=forms.DateInput(attrs={"type": "date", "class": "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-xs font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white"}, format="%Y-%m-%d"),
    )
    receptor = forms.CharField(
        label="Recibió la entrega", max_length=200,
        widget=forms.TextInput(attrs={"class": "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-xs font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white", "placeholder": "Nombre de quien recibió"}),
    )


class CancelacionForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo de la cancelación", min_length=10,
        widget=forms.Textarea(attrs={"rows": 3, "class": "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-xs font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white"}),
        help_text="Ej. Error en el número de serie del equipo X.",
    )


class AdjuntoForm(forms.Form):
    rol = forms.CharField(required=False, widget=forms.HiddenInput)
    archivo = forms.FileField(
        label="Archivo (PDF o foto)",
        widget=forms.ClearableFileInput(attrs={"accept": "application/pdf,image/*", "class": "w-full cursor-pointer rounded-xl border border-gray-200 bg-gray-50/70 text-xs font-mono text-gray-600 file:mr-3 file:cursor-pointer file:rounded-l-xl file:border-0 file:bg-brand-primary file:px-4 file:py-2.5 file:text-xs file:font-black file:uppercase file:tracking-widest file:text-white hover:file:brightness-110"}),
    )


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
    categoria = forms.ChoiceField(label="Categoría", required=False)
    tab = forms.CharField(required=False, widget=forms.HiddenInput)
    desde = forms.DateField(label="Desde", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    hasta = forms.DateField(label="Hasta", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    def __init__(self, *args, direcciones=None, gestores=(), categorias=(), **kwargs):
        super().__init__(*args, **kwargs)
        if direcciones is not None:
            self.fields["direccion"].queryset = direcciones
        self.fields["categoria"].choices = [("", "Todas las categorías"), ("sin", "Sin categoría")] + [
            (str(c.pk), c.nombre) for c in categorias
        ]
        self.fields["gestor"].choices = [("", "Todos los gestores"), ("sin", "Sin gestor")] + [
            (str(g.pk), g.nombre) for g in gestores
        ]
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-xs font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white")


class DireccionForm(forms.ModelForm):
    dependencia = forms.ChoiceField(
        label="Dependencia del Core", required=False,
        help_text="Define quién ve los documentos de esta dirección. Sin vincular, solo los ve el administrador global.",
    )

    class Meta:
        model = Direccion
        fields = ["nombre", "folio_manual", "vales_habilitados", "soporte_habilitado", "is_active"]
        labels = {
            "is_active": "Activa", "folio_manual": "Folio manual", "vales_habilitados": "Vales de préstamo",
            "soporte_habilitado": "Soporte técnico",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dependencia"].choices = [("", "Sin vincular")] + [
            (str(pk), nombre) for pk, nombre in dependencias_del_core()
        ]
        if self.instance.dependencia_uuid:
            self.fields["dependencia"].initial = str(self.instance.dependencia_uuid)
        for nombre, campo in self.fields.items():
            if nombre not in ("is_active", "folio_manual", "vales_habilitados", "soporte_habilitado"):
                campo.widget.attrs.setdefault("class", "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-xs font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white")

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
            campo.widget.attrs.setdefault("class", "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-xs font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white")

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
    categoria = forms.ModelChoiceField(label="Categoría", required=False, queryset=Categoria.objects.none(), empty_label="Sin categoría")

    def clean(self):
        datos = super().clean()
        _resolver_contraparte(self, datos, getattr(self.documento.direccion, "dependencia_uuid", None))
        return datos

    def __init__(self, *args, documento, **kwargs):
        super().__init__(*args, **kwargs)
        self.documento = documento
        self.fields["categoria"].queryset = Categoria.objects.filter(
            Q(is_active=True, is_deleted=False) | Q(pk=documento.categoria_id), direccion=documento.direccion
        )
        _agregar_contraparte(
            self, "Dirección destinataria" if documento.sentido == "enviado" else "Dirección remitente"
        )
        if documento.contraparte_dependencia_uuid:
            self.initial.setdefault("contraparte_dependencia", str(documento.contraparte_dependencia_uuid))
        self.order_fields(["contraparte_dependencia", "contraparte", "asunto", "fecha", "folio", "categoria", "gestor", "motivo"])
        if documento.sentido == "enviado":
            if not documento.folio_manual:
                self.fields.pop("folio")
            if "folio" in self.fields:
                self.fields["folio"].label = "Folio del oficio"
            self.fields["gestor"].queryset = Gestor.objects.filter(
                Q(usuario__isnull=False) | Q(pk=documento.gestor_id),
                direccion=documento.direccion, is_active=True, is_deleted=False,
            )
        else:
            self.fields.pop("gestor")
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-xs font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white")


class GestorForm(forms.ModelForm):
    """Un gestor es siempre un usuario existente con membresía en el módulo; el nombre sale de su cuenta."""

    class Meta:
        model = Gestor
        fields = ["usuario"]
        labels = {"usuario": "Usuario"}

    def __init__(self, *args, direccion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.direccion = direccion or getattr(self.instance, "direccion", None)
        self.fields["usuario"].queryset = usuarios_con_acceso("seguimientos_oficios")
        self.fields["usuario"].required = True
        self.fields["usuario"].empty_label = "Elija un usuario"

    def clean_usuario(self):
        usuario = self.cleaned_data["usuario"]
        if Gestor.objects.filter(direccion=self.direccion, usuario=usuario).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ese usuario ya es gestor de esta dirección.")
        return usuario

class FiltroBusquedaForm(FiltroDocumentosForm):
    """Filtros de la vista de búsqueda: el texto manda; el resto acota (sentido, clase, dirección, fechas)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for sobrante in ("estado", "gestor", "tab"):
            self.fields.pop(sobrante)
        self.fields["q"].widget.attrs["placeholder"] = "Palabra o frase dentro de los documentos, folio, asunto…"


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre"]

    def __init__(self, *args, direccion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.direccion = direccion or getattr(self.instance, "direccion", None)
        self.fields["nombre"].widget.attrs.setdefault(
            "class", "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-xs font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white"
        )

    def clean_nombre(self):
        nombre = " ".join(self.cleaned_data["nombre"].split())
        repetida = Categoria.objects.filter(direccion=self.direccion, nombre__iexact=nombre).exclude(pk=self.instance.pk)
        if repetida.exists() or any(
            c.nombre.casefold() == nombre.casefold()
            for c in Categoria.objects.filter(direccion=self.direccion).exclude(pk=self.instance.pk)
        ):
            raise forms.ValidationError("Ya existe una categoría con ese nombre en esta dirección.")
        return nombre


class GestorEntregaForm(forms.Form):
    fecha_entrega = forms.DateField(
        label="Fecha de entrega", required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-xs font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white"}, format="%Y-%m-%d"),
    )
    receptor = forms.CharField(
        label="Quién recibió", max_length=200, required=False,
        widget=forms.TextInput(attrs={"class": "w-full rounded-xl border border-gray-200 bg-gray-50/70 px-3 py-2.5 text-xs font-mono font-medium text-gray-700 outline-none focus:border-gray-950 focus:bg-white", "placeholder": "Nombre de quien recibió"}),
    )
    archivo = forms.FileField(
        label="Foto o PDF del acuse", required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/*,application/pdf", "class": "w-full cursor-pointer rounded-xl border border-gray-200 bg-gray-50/70 text-xs font-mono text-gray-600 file:mr-3 file:cursor-pointer file:rounded-l-xl file:border-0 file:bg-brand-primary file:px-4 file:py-2.5 file:text-xs file:font-black file:uppercase file:tracking-widest file:text-white hover:file:brightness-110"}),
    )
