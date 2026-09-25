from django import forms
from django.utils import timezone

from ..forms import _agregar_contraparte, _resolver_contraparte
from ..integracion import director_de_dependencia
from ..models import Gestor
from ..prestamos.forms import CLASE
from .services import CLASIFICACIONES, COMPONENTES, DISPOSICIONES, RECOMENDACIONES

CAMPOS_EQUIPO = ("equipo", "marca_modelo", "serie", "folio_inventario", "departamento", "info_tecnica")
CARGO_TECNICO = "Técnico de Soporte en TI"


def leer_equipos(post, bienes):
    """Renglones de equipos del formulario (`eq-N-campo`) ya limpios. Los vacíos se omiten.

    Si el renglón trae un bien del catálogo (`eq-N-bien`), ese bien manda: debe estar entre los permitidos.
    """
    permitidos = {str(b.pk): b for b in bienes}
    indices = sorted({int(k.split("-")[1]) for k in post if k.startswith("eq-") and k.split("-")[1].isdigit()})
    equipos, errores = [], []
    for i in indices:
        fila = {c: (post.get(f"eq-{i}-{c}") or "").strip()[:150] for c in CAMPOS_EQUIPO if c != "info_tecnica"}
        bien_id = post.get(f"eq-{i}-bien") or ""
        if not any(fila.values()) and not bien_id:
            continue
        if bien_id:
            bien = permitidos.get(bien_id)
            if bien is None:
                errores.append("Uno de los bienes elegidos ya no está disponible.")
                continue
            fila["bien"] = bien
            fila["equipo"] = fila["equipo"] or bien.nombre
            fila["marca_modelo"] = fila["marca_modelo"] or bien.marca_modelo
            fila["serie"] = fila["serie"] or bien.identificador
            fila["folio_inventario"] = fila["folio_inventario"] or bien.folio_inventario
        if not fila["equipo"]:
            errores.append("Cada equipo necesita al menos su descripción.")
            continue
        equipos.append(fila)
    return equipos, errores


def leer_componentes(post, bienes):
    """Los cuatro componentes del resguardo (`eq-N-campo`, N = 0 a 3), siempre en el mismo orden; los vacíos quedan en blanco.

    Si el componente trae un bien del catálogo (`eq-N-bien`) y sus datos vienen vacíos, se toman del bien."""
    permitidos = {str(b.pk): b for b in bienes}
    filas, errores = [], []
    for i, (tipo, nombre) in enumerate(COMPONENTES):
        fila = {c: (post.get(f"eq-{i}-{c}") or "").strip()[:150] for c in ("marca_modelo", "serie", "folio_inventario")}
        fila.update(equipo=nombre, tipo=tipo, departamento="", info_tecnica=(post.get(f"eq-{i}-info_tecnica") or "").strip()[:1000])
        bien_id = post.get(f"eq-{i}-bien") or ""
        if bien_id:
            bien = permitidos.get(bien_id)
            if bien is None:
                errores.append(f"El bien elegido para {nombre.lower()} ya no está disponible.")
            else:
                fila["bien"] = bien
                fila["marca_modelo"] = fila["marca_modelo"] or bien.marca_modelo
                fila["serie"] = fila["serie"] or bien.identificador
                fila["folio_inventario"] = fila["folio_inventario"] or bien.folio_inventario
        filas.append(fila)
    return filas, errores


def leer_equipos_edicion(post):
    """Renglones de una edición (`eq-N-id` + textos): {id: textos}. No se agregan ni quitan renglones."""
    indices = sorted({int(k.split("-")[1]) for k in post if k.startswith("eq-") and k.split("-")[1].isdigit()})
    equipos = {}
    for i in indices:
        identificador = post.get(f"eq-{i}-id")
        if identificador:
            equipos[identificador] = {c: (post.get(f"eq-{i}-{c}") or "").strip()[:1000 if c == "info_tecnica" else 150] for c in CAMPOS_EQUIPO}
    return equipos


def _fecha():
    return forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))


class SoporteBase(forms.Form):
    direccion = forms.ModelChoiceField(label="Dirección que emite", queryset=None)
    ticket = forms.CharField(label="Ticket de la mesa de ayuda", max_length=60, required=False)
    elaboro_cargo = forms.CharField(label="Cargo de quien elabora", max_length=200, initial=CARGO_TECNICO)
    OCULTOS = ("direccion",)
    FIRMAS = ("elaboro_cargo", "autoriza_nombre", "autoriza_cargo")

    def clean(self):
        datos = super().clean()
        direccion, gestor = datos.get("direccion"), datos.get("gestor")
        if direccion and gestor and gestor.direccion_id != direccion.pk:
            self.add_error("gestor", "El gestor no pertenece a la dirección.")
        return datos

    @property
    def grupos(self):
        """Campos por bloque de la pantalla: datos, opciones (radios) y firmas; la dirección va aparte."""
        campos = [c for c in self if c.name != "direccion"]
        return {
            "datos": [c for c in campos if c.name not in self.FIRMAS and not isinstance(c.field.widget, forms.RadioSelect)],
            "opciones": [c for c in campos if isinstance(c.field.widget, forms.RadioSelect)],
            "firmas": [c for c in campos if c.name in self.FIRMAS],
        }

    def __init__(self, *args, direcciones, edicion=False, gestores=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.edicion = edicion
        self.fields["direccion"].queryset = direcciones
        self.fields["gestor"] = forms.ModelChoiceField(
            label="Gestor (quien lo lleva a la dependencia)", required=False, empty_label="Sin asignar",
            queryset=gestores if gestores is not None else Gestor.objects.none(),
        )
        self.mostrar_direccion = direcciones.count() != 1
        if not self.mostrar_direccion:
            self.fields["direccion"].initial = direcciones.first().pk
            self.fields["direccion"].widget = forms.HiddenInput()
        if edicion:
            self.fields["motivo"] = forms.CharField(
                label="Motivo de la corrección", required=False, max_length=300,
                help_text="Obligatorio si el documento ya se firmó o entregó.",
            )
            self.FIRMAS = self.FIRMAS + ("motivo",)
        for nombre, campo in self.fields.items():
            if nombre not in self.OCULTOS or (nombre == "direccion" and self.mostrar_direccion):
                campo.widget.attrs.setdefault("class", CLASE)


class _ConAutoriza(forms.Form):
    def _agregar_autoriza(self, direcciones):
        self.fields["autoriza_nombre"] = forms.CharField(label="Autoriza (nombre)", max_length=200)
        self.fields["autoriza_cargo"] = forms.CharField(
            label="Autoriza (cargo)", max_length=200,
            help_text="Jefe de departamento, subdirector o director.",
        )
        primera = direcciones.first() if direcciones.count() == 1 else None
        if primera:
            self.fields["autoriza_nombre"].initial = director_de_dependencia(primera.dependencia_uuid)
        for nombre in ("autoriza_nombre", "autoriza_cargo"):
            self.fields[nombre].widget.attrs.setdefault("class", CLASE)


class DiagnosticoForm(SoporteBase):
    solicitante = forms.CharField(label="Solicitó (nombre)", max_length=200)
    fecha_recibido = _fecha()
    tipo_bien = forms.CharField(label="Tipo de bien", max_length=120, required=False)
    fallo = forms.CharField(label="Fallo", widget=forms.Textarea(attrs={"rows": 2}))
    causa = forms.CharField(label="Causa", widget=forms.Textarea(attrs={"rows": 2}))
    solucion = forms.CharField(label="Solución", widget=forms.Textarea(attrs={"rows": 2}))
    observaciones = forms.CharField(label="Observaciones", required=False, widget=forms.Textarea(attrs={"rows": 3}))
    recomendacion = forms.ChoiceField(label="Recomendación sobre el bien", choices=RECOMENDACIONES, widget=forms.RadioSelect)
    OCULTOS = ("direccion", "recomendacion")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha_recibido"].label = "Fecha de recibido"
        self.fields["fecha_recibido"].initial = timezone.localdate()
        self.fields["fecha_recibido"].widget.attrs.setdefault("class", CLASE)


class BajaForm(SoporteBase, _ConAutoriza):
    contraparte = forms.CharField(max_length=200, required=False)
    diagnostico = forms.CharField(label="Diagnóstico", widget=forms.Textarea(attrs={"rows": 4}))
    solicitante = forms.CharField(label="Solicitó el dictamen (nombre)", max_length=200)
    clasificacion = forms.ChoiceField(label="Clasificación de no utilidad", choices=CLASIFICACIONES, widget=forms.RadioSelect)
    disposicion = forms.ChoiceField(label="Recomendación de disposición final", choices=DISPOSICIONES, widget=forms.RadioSelect)
    OCULTOS = ("direccion", "clasificacion", "disposicion")

    def __init__(self, *args, direcciones, **kwargs):
        super().__init__(*args, direcciones=direcciones, **kwargs)
        _agregar_contraparte(self, "Área que identifica y solicita el dictamen")
        self.fields["contraparte_dependencia"].widget.attrs.setdefault("class", CLASE)
        self.fields["contraparte"].widget.attrs.setdefault("class", CLASE)
        self._agregar_autoriza(direcciones)

    def clean(self):
        datos = super().clean()
        _resolver_contraparte(self, datos, getattr(datos.get("direccion"), "dependencia_uuid", None))
        return datos


class AltaForm(SoporteBase, _ConAutoriza):
    contraparte = forms.CharField(max_length=200, required=False)
    solicitud = forms.CharField(label="Solicitud", widget=forms.Textarea(attrs={"rows": 4}))
    justificacion = forms.CharField(label="Justificación", widget=forms.Textarea(attrs={"rows": 4}))
    dictamen = forms.CharField(label="Dictamen", widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, direcciones, **kwargs):
        super().__init__(*args, direcciones=direcciones, **kwargs)
        _agregar_contraparte(self, "Dirección o departamento al que se dirige")
        self.fields["contraparte_dependencia"].widget.attrs.setdefault("class", CLASE)
        self.fields["contraparte"].widget.attrs.setdefault("class", CLASE)
        self._agregar_autoriza(direcciones)

    def clean(self):
        datos = super().clean()
        _resolver_contraparte(self, datos, getattr(datos.get("direccion"), "dependencia_uuid", None))
        return datos


class ResguardoForm(SoporteBase, _ConAutoriza):
    contraparte = forms.CharField(max_length=200, required=False)
    fecha_entrega = _fecha()
    empleado = forms.CharField(label="Empleado a quien se le asigna el equipo", max_length=200)

    def __init__(self, *args, direcciones, **kwargs):
        super().__init__(*args, direcciones=direcciones, **kwargs)
        _agregar_contraparte(self, "Departamento")
        self.fields["fecha_entrega"].label = "Fecha de entrega"
        self.fields["fecha_entrega"].initial = timezone.localdate()
        self.fields["fecha_entrega"].widget.attrs.setdefault("class", CLASE)
        self.fields["contraparte_dependencia"].widget.attrs.setdefault("class", CLASE)
        self.fields["contraparte"].widget.attrs.setdefault("class", CLASE)
        self.fields["ticket"].label = "Ticket de la mesa de ayuda (opcional)"
        self._agregar_autoriza(direcciones)

    def clean(self):
        datos = super().clean()
        _resolver_contraparte(self, datos, getattr(datos.get("direccion"), "dependencia_uuid", None))
        return datos
