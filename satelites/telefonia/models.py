import re
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def normalizar_identificador(valor):
    """Número o circuito sin espacios y en mayúsculas: '9212 165053' y '9212165053 ' son la misma línea."""
    return re.sub(r"\s+", "", valor or "").upper()


class BaseTel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField("Activo", default=True)
    is_deleted = models.BooleanField("Eliminado", default=False, db_index=True)
    created_at = models.DateTimeField("Creado", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        abstract = True


class Linea(BaseTel):
    """Línea telefónica, servicio de internet o enlace dedicado de un sitio del municipio."""

    class Tipo(models.TextChoices):
        TELEFONO = "telefono", "Línea telefónica"
        INTERNET = "internet", "Internet"
        ENLACE = "enlace", "Enlace dedicado"
        OTRO = "otro", "Otro"

    identificador = models.CharField(
        "Número o circuito", max_length=60,
        help_text="Número telefónico o identificador del enlace (p. ej. C1G-2204-0353).",
    )
    identificador_normalizado = models.CharField(max_length=60, unique=True, editable=False)
    sitio = models.CharField("Sitio", max_length=150)
    municipio = models.CharField("Municipio", max_length=100, default="Coatzacoalcos")
    direccion = models.CharField("Dirección", max_length=255, blank=True)
    tipo = models.CharField("Tipo", max_length=10, choices=Tipo.choices, default=Tipo.TELEFONO)
    velocidad = models.CharField("Paquete o velocidad", max_length=80, blank=True, help_text="Ej. 300 Mb simétrico.")
    latitud = models.DecimalField("Latitud", max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField("Longitud", max_digits=9, decimal_places=6, null=True, blank=True)
    notas = models.TextField("Notas", blank=True)

    class Meta:
        db_table = "tel_linea"
        ordering = ["sitio", "identificador"]
        verbose_name = "Línea"
        verbose_name_plural = "Líneas"

    def __str__(self):
        return f"{self.identificador} · {self.sitio}"

    def save(self, *args, **kwargs):
        self.identificador = " ".join((self.identificador or "").split())
        self.identificador_normalizado = normalizar_identificador(self.identificador)
        super().save(*args, **kwargs)

    @property
    def con_ubicacion(self):
        return self.latitud is not None and self.longitud is not None

    @property
    def enlace_google_maps(self):
        if not self.con_ubicacion:
            return ""
        return f"https://www.google.com/maps?q={self.latitud},{self.longitud}"


class Reporte(BaseTel):
    """Reporte de falla levantado a Telmex (con su folio) y su seguimiento hasta que queda atendido."""

    class Estatus(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ATENDIDO = "atendido", "Atendido"
        CANCELADO = "cancelado", "Cancelado"

    linea = models.ForeignKey(Linea, on_delete=models.PROTECT, related_name="reportes", verbose_name="Línea")
    linea_texto = models.CharField(max_length=60, editable=False)
    sitio_texto = models.CharField(max_length=150, editable=False)
    folio = models.CharField("Folio de Telmex", max_length=40)
    folio_normalizado = models.CharField(max_length=40, unique=True, editable=False)
    estatus = models.CharField("Estatus", max_length=10, choices=Estatus.choices, default=Estatus.PENDIENTE, db_index=True)
    levantado = models.DateField("Levantado")
    atendido = models.DateField("Atendido", null=True, blank=True)
    detalle = models.TextField("Detalle de la falla", blank=True)
    contacto_nombre = models.CharField("Contacto en sitio", max_length=150)
    contacto_telefono = models.CharField("Teléfono del contacto", max_length=30)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name="Responsable de Innovación",
    )
    responsable_nombre = models.CharField(max_length=200, blank=True, editable=False)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    motivo_cancelacion = models.TextField(blank=True)

    class Meta:
        db_table = "tel_reporte"
        ordering = ["-levantado", "-created_at"]
        verbose_name = "Reporte"
        verbose_name_plural = "Reportes"

    def __str__(self):
        return f"{self.folio} · {self.linea_texto}"

    def save(self, *args, **kwargs):
        self.folio = " ".join((self.folio or "").split())
        self.folio_normalizado = normalizar_identificador(self.folio)
        super().save(*args, **kwargs)

    @property
    def abierto(self):
        return self.estatus == self.Estatus.PENDIENTE

    @property
    def dias_abierto(self):
        """Días desde que se levantó hasta hoy (pendiente) o hasta que se atendió."""
        fin = self.atendido if self.atendido else timezone.localdate()
        return max(0, (fin - self.levantado).days)

    @property
    def color(self):
        from .selectors import color_semaforo

        return color_semaforo(self.dias_abierto) if self.abierto else ""


class Movimiento(models.Model):
    """Bitácora del reporte: solo se escribe. Aquí viven los comentarios que van dando contexto de visita en visita."""

    class Tipo(models.TextChoices):
        CREADO = "creado", "Reporte levantado"
        COMENTARIO = "comentario", "Comentario"
        EVIDENCIA = "evidencia", "Evidencia"
        ATENDIDO = "atendido", "Marcado como atendido"
        CANCELADO = "cancelado", "Cancelado"
        REABIERTO = "reabierto", "Reabierto"
        EDITADO = "editado", "Datos corregidos"
        RESPONSABLE = "responsable", "Responsable"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporte = models.ForeignKey(Reporte, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    usuario_nombre = models.CharField(max_length=200, blank=True)
    texto = models.TextField(blank=True)
    datos = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "tel_movimiento"
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("La bitácora del reporte es de solo escritura.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("La bitácora del reporte no se puede borrar.")


class Evidencia(BaseTel):
    """Foto o captura (prueba de velocidad, etc.) que respalda un reporte. Opcional."""

    class Tipo(models.TextChoices):
        FOTO = "foto", "Foto"
        VELOCIDAD = "velocidad", "Prueba de velocidad"
        OTRA = "otra", "Otra"

    reporte = models.ForeignKey(Reporte, on_delete=models.PROTECT, related_name="evidencias")
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.FOTO)
    ruta = models.CharField(max_length=300, editable=False)
    nombre_original = models.CharField(max_length=200)
    content_type = models.CharField(max_length=60)
    tamano = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True, editable=False)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    subido_por_nombre = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "tel_evidencia"
        ordering = ["created_at"]

    @property
    def es_imagen(self):
        return self.content_type.startswith("image/")
