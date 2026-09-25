import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .textos import normalizar
from django.db.models import Q


class BaseOficios(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField("Activo", default=True)
    is_deleted = models.BooleanField("Eliminado", default=False, db_index=True)
    created_at = models.DateTimeField("Creado", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        abstract = True


class ClaseDocumento(models.TextChoices):
    OFICIO = "oficio", "Oficio"
    VALE_PRESTAMO = "vale_prestamo", "Vale de préstamo"
    DIAGNOSTICO_TECNICO = "diagnostico_tecnico", "Diagnóstico técnico"
    DICTAMEN_ALTA = "dictamen_alta", "Dictamen de alta"
    DICTAMEN_BAJA = "dictamen_baja", "Dictamen de baja"
    COMUNICADO = "comunicado", "Comunicado"
    OTRO = "otro", "Otro"


class Direccion(BaseOficios):
    """Dirección propia de la app; se vincula al Core solo por UUID."""

    nombre = models.CharField("Nombre", max_length=150, unique=True)
    slug = models.SlugField(
        "Carpeta de archivos", max_length=160, unique=True, null=True, editable=False,
        help_text="Nombre de carpeta en el almacén; se fija al crear la dirección y no cambia si se renombra.",
    )
    folio_manual = models.BooleanField(
        "Folio manual", default=True,
        help_text="Activo: quien registra un oficio enviado escribe su folio. Inactivo: se genera con la nomenclatura.",
    )
    dependencia_uuid = models.UUIDField(
        "Dependencia del Core",
        null=True,
        blank=True,
        db_index=True,
        help_text="UUID de la dependencia del Core que define quién ve estos oficios.",
    )

    class Meta:
        db_table = "oficios_direccion"
        ordering = ["nombre"]
        verbose_name = "Dirección"
        verbose_name_plural = "Direcciones"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.slug_libre(self.nombre)
        super().save(*args, **kwargs)

    @classmethod
    def slug_libre(cls, nombre):
        base = slugify(nombre) or "direccion"
        candidato, n = base, 2
        while cls.objects.filter(slug=candidato).exists():
            candidato, n = f"{base}-{n}", n + 1
        return candidato


class Nomenclatura(BaseOficios):
    """Formato de folio de una clase de documento enviado por una dirección."""

    PLANTILLA_VALIDA = re.compile(r"\{(n|n:0\d+d|anio)\}")

    direccion = models.ForeignKey(Direccion, on_delete=models.PROTECT, related_name="nomenclaturas")
    clase = models.CharField("Clase de documento", max_length=25, choices=ClaseDocumento.choices)
    plantilla = models.CharField(
        "Plantilla", max_length=60, default="{n:03d}/{anio}",
        help_text="Ej. IN-{n:03d}/{anio} da IN-001/2026. Tokens: {n}, {n:03d} y {anio}.",
    )

    class Meta:
        db_table = "oficios_nomenclatura"
        ordering = ["direccion__nombre", "clase"]
        verbose_name = "Nomenclatura"
        verbose_name_plural = "Nomenclaturas"
        constraints = [
            models.UniqueConstraint(fields=["direccion", "clase"], name="oficios_nomenclatura_unica")
        ]

    def __str__(self):
        return f"{self.direccion} / {self.get_clase_display()}: {self.plantilla}"

    def clean(self):
        resto = self.PLANTILLA_VALIDA.sub("", self.plantilla or "")
        if "{n" not in self.plantilla or "{" in resto or "}" in resto:
            raise ValidationError({"plantilla": "Plantilla inválida: use {n}, {n:03d} y {anio}."})

    @property
    def ejemplo(self):
        from datetime import date

        return self.formatear(1, date.today().year)

    def formatear(self, numero, anio):
        return self.plantilla.format(n=numero, anio=anio)

    def interpretar(self, texto, *, buscar=False, tolerante=False):
        """(numero, anio) si el texto sigue la plantilla; anio es None si la plantilla no lo lleva."""
        patron, resto = "", self.plantilla
        for pieza in re.split(r"(\{[^}]*\})", resto):
            if pieza.startswith("{n"):
                patron += r"(?P<n>\d+)"
            elif pieza == "{anio}":
                patron += r"(?P<anio>\d{4})"
            else:
                patron += re.escape(pieza).replace("/", "[/_-]" if tolerante else "/")
        coincidencia = (re.search if buscar else re.fullmatch)(patron, texto or "")
        if not coincidencia:
            return None
        grupos = coincidencia.groupdict()
        return int(grupos["n"]), int(grupos["anio"]) if grupos.get("anio") else None


class Gestor(BaseOficios):
    """Quien lleva los oficios a la dependencia destino y trae la evidencia."""

    direccion = models.ForeignKey(Direccion, on_delete=models.PROTECT, related_name="gestores")
    nombre = models.CharField("Nombre", max_length=150)

    class Meta:
        db_table = "oficios_gestor"
        ordering = ["nombre"]
        verbose_name = "Gestor"
        verbose_name_plural = "Gestores"
        constraints = [
            models.UniqueConstraint(fields=["direccion", "nombre"], name="oficios_gestor_unico"),
        ]

    def __str__(self):
        return self.nombre


class ConsecutivoFolio(models.Model):
    nomenclatura = models.ForeignKey(Nomenclatura, on_delete=models.PROTECT, related_name="consecutivos")
    anio = models.PositiveSmallIntegerField("Año")
    ultimo = models.PositiveIntegerField("Último número", default=0)

    class Meta:
        db_table = "oficios_consecutivo"
        constraints = [
            models.UniqueConstraint(fields=["nomenclatura", "anio"], name="oficios_consecutivo_unico")
        ]


class Documento(BaseOficios):
    class Sentido(models.TextChoices):
        RECIBIDO = "recibido", "Recibido"
        ENVIADO = "enviado", "Enviado"

    class Estado(models.TextChoices):
        REGISTRADO = "registrado", "Registrado"
        GENERADO = "generado", "Generado"
        ENTREGADO = "entregado", "Entregado"
        CONCLUIDO = "concluido", "Concluido"
        CANCELADO = "cancelado", "Cancelado"

    INMUTABLES = ("sentido", "clase", "direccion_id", "direccion_nombre", "director_nombre",
                  "anio", "consecutivo")

    sentido = models.CharField("Sentido", max_length=10, choices=Sentido.choices)
    clase = models.CharField("Clase de documento", max_length=25, choices=ClaseDocumento.choices, default=ClaseDocumento.OFICIO)
    direccion = models.ForeignKey(
        Direccion, on_delete=models.PROTECT, related_name="documentos", verbose_name="Dirección"
    )
    direccion_nombre = models.CharField("Dirección (al registrar)", max_length=150)
    contraparte = models.CharField(
        "Remitente o destinatario", max_length=200,
        help_text="Nombre de quien envía (recibidos) o a quién se dirige (enviados).",
    )
    contraparte_dependencia_uuid = models.UUIDField(
        "Dependencia remitente o destinataria", null=True, blank=True, editable=False,
        help_text="UUID de la dependencia del Core cuando la contraparte es una dirección de la institución.",
    )
    director_nombre = models.CharField("Director (al registrar)", max_length=200, blank=True)
    asunto = models.CharField("Asunto", max_length=300)
    fecha = models.DateField("Fecha del documento")
    folio = models.CharField("Folio", max_length=80, blank=True, db_index=True)
    folio_manual = models.BooleanField("Folio capturado a mano", default=False)
    anio = models.PositiveSmallIntegerField(null=True, blank=True)
    consecutivo = models.PositiveIntegerField(null=True, blank=True)
    gestor = models.ForeignKey(
        Gestor, null=True, blank=True, on_delete=models.PROTECT, related_name="documentos",
        verbose_name="Gestor",
    )
    busqueda = models.TextField(editable=False, blank=True, default="")
    estado = models.CharField("Estado", max_length=12, choices=Estado.choices, default=Estado.GENERADO, db_index=True)
    fecha_entrega = models.DateField("Fecha de entrega", null=True, blank=True)
    receptor_entrega = models.CharField("Recibió la entrega", max_length=200, blank=True)
    motivo_cancelacion = models.TextField("Motivo de cancelación", blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        db_table = "oficios_documento"
        ordering = ["-fecha", "-created_at"]
        verbose_name = "Documento"
        verbose_name_plural = "Documentos"
        constraints = [
            models.UniqueConstraint(
                fields=["direccion", "folio"],
                condition=Q(sentido="enviado"),
                name="oficios_folio_enviado_unico",
            )
        ]

    def __str__(self):
        return f"{self.folio or 's/f'} - {self.asunto[:60]}"

    @property
    def dias_pendiente(self):
        if self.estado not in (self.Estado.GENERADO, self.Estado.ENTREGADO):
            return None
        desde = self.fecha_entrega or timezone.localtime(self.created_at).date()
        return (timezone.localdate() - desde).days

    def save(self, *args, **kwargs):
        self.busqueda = normalizar(" ".join((self.folio, self.asunto, self.contraparte, self.director_nombre)))
        if not self._state.adding:
            protegidos = self.INMUTABLES + (("folio",) if self.sentido == self.Sentido.ENVIADO and not self.folio_manual else ())
            original = type(self).objects.filter(pk=self.pk).values(*protegidos).first()
            if original:
                cambiados = [c for c in protegidos if original[c] != getattr(self, c)]
                if cambiados:
                    raise ValueError(f"Campos inmutables: {', '.join(cambiados)}")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Los documentos no se eliminan; se cancelan con motivo.")


class HistorialDocumento(models.Model):
    """Bitácora append-only de cada documento."""

    class Accion(models.TextChoices):
        CREADO = "creado", "Creado"
        EDITADO = "editado", "Editado"
        ADJUNTADO = "adjuntado", "Adjunto agregado"
        QUITADO = "quitado", "Archivo quitado"
        ELIMINADO = "eliminado", "Eliminado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    documento = models.ForeignKey(Documento, on_delete=models.PROTECT, related_name="historial")
    accion = models.CharField(max_length=12, choices=Accion.choices)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    usuario_nombre = models.CharField(max_length=200, blank=True)
    datos = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "oficios_historial"
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("El historial es de solo escritura.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("El historial no se puede borrar.")


class Adjunto(models.Model):
    """Archivo (PDF) de un documento. Solo se agrega; nunca se borra ni se reemplaza."""

    class Rol(models.TextChoices):
        ORIGINAL = "original", "Original escaneado"
        FIRMADO = "firmado", "Documento firmado"
        EVIDENCIA = "evidencia", "Evidencia de entrega"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    documento = models.ForeignKey(Documento, on_delete=models.PROTECT, related_name="adjuntos")
    rol = models.CharField(max_length=10, choices=Rol.choices)
    ruta = models.CharField("Ruta en el almacén", max_length=255)
    nombre_original = models.CharField(max_length=255)
    sha256 = models.CharField("SHA-256", max_length=64, db_index=True)
    tamano = models.PositiveBigIntegerField("Tamaño (bytes)")
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    subido_por_nombre = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    eliminado = models.BooleanField(default=False, db_index=True)
    eliminado_motivo = models.TextField(blank=True)
    eliminado_por_nombre = models.CharField(max_length=200, blank=True)
    eliminado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "oficios_adjunto"
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Los adjuntos no se modifican.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Los adjuntos no se eliminan.")


class AdjuntoOCR(models.Model):
    """Texto extraído de un adjunto; el PDF original nunca se altera."""

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PROCESANDO = "procesando", "Procesando"
        LISTO = "listo", "Listo"
        ERROR = "error", "Error"

    adjunto = models.OneToOneField(Adjunto, on_delete=models.PROTECT, related_name="ocr")
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    texto = models.TextField(blank=True)
    texto_normalizado = models.TextField(editable=False, blank=True, default="")
    error = models.TextField(blank=True)
    intentos = models.PositiveSmallIntegerField(default=0)
    iniciado_en = models.DateTimeField(null=True, blank=True)
    terminado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "oficios_adjunto_ocr"

    def save(self, *args, **kwargs):
        self.texto_normalizado = normalizar(self.texto)
        super().save(*args, **kwargs)
