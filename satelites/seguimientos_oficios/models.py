import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class BaseOficios(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_active = models.BooleanField("Activo", default=True)
    is_deleted = models.BooleanField("Eliminado", default=False, db_index=True)
    created_at = models.DateTimeField("Creado", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        abstract = True


class Direccion(BaseOficios):
    """Dirección propia de la app; se vincula al Core solo por UUID."""

    nombre = models.CharField("Nombre", max_length=150, unique=True)
    prefijo = models.CharField(
        "Prefijo de folio", max_length=10, blank=True,
        help_text="Ej. IN. Necesario para generar folios de los oficios enviados.",
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


class ConsecutivoFolio(models.Model):
    direccion = models.ForeignKey(Direccion, on_delete=models.PROTECT, related_name="consecutivos")
    anio = models.PositiveSmallIntegerField("Año")
    ultimo = models.PositiveIntegerField("Último número", default=0)

    class Meta:
        db_table = "oficios_consecutivo"
        constraints = [
            models.UniqueConstraint(fields=["direccion", "anio"], name="oficios_consecutivo_unico")
        ]


class Documento(BaseOficios):
    class Sentido(models.TextChoices):
        RECIBIDO = "recibido", "Recibido"
        ENVIADO = "enviado", "Enviado"

    class Clase(models.TextChoices):
        OFICIO = "oficio", "Oficio"
        VALE_PRESTAMO = "vale_prestamo", "Vale de préstamo"
        DIAGNOSTICO_TECNICO = "diagnostico_tecnico", "Diagnóstico técnico"
        DICTAMEN_ALTA = "dictamen_alta", "Dictamen de alta"
        DICTAMEN_BAJA = "dictamen_baja", "Dictamen de baja"
        COMUNICADO = "comunicado", "Comunicado"
        OTRO = "otro", "Otro"

    INMUTABLES = ("sentido", "clase", "direccion_id", "direccion_nombre", "director_nombre",
                  "folio", "anio", "consecutivo")

    sentido = models.CharField("Sentido", max_length=10, choices=Sentido.choices)
    clase = models.CharField("Clase de documento", max_length=25, choices=Clase.choices, default=Clase.OFICIO)
    direccion = models.ForeignKey(
        Direccion, on_delete=models.PROTECT, related_name="documentos", verbose_name="Dirección"
    )
    direccion_nombre = models.CharField("Dirección (al registrar)", max_length=150)
    contraparte = models.CharField(
        "Remitente o destinatario", max_length=200,
        help_text="Quién envía (recibidos) o a quién se dirige (enviados).",
    )
    director_nombre = models.CharField("Director (al registrar)", max_length=200, blank=True)
    asunto = models.CharField("Asunto", max_length=300)
    fecha = models.DateField("Fecha del documento")
    folio = models.CharField("Folio", max_length=80, blank=True, db_index=True)
    anio = models.PositiveSmallIntegerField(null=True, blank=True)
    consecutivo = models.PositiveIntegerField(null=True, blank=True)
    archivo_hash = models.CharField("SHA-256", max_length=64, blank=True, db_index=True)
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

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = type(self).objects.filter(pk=self.pk).values(*self.INMUTABLES).first()
            if original:
                cambiados = [c for c in self.INMUTABLES if original[c] != getattr(self, c)]
                if cambiados:
                    raise ValueError(f"Campos inmutables: {', '.join(cambiados)}")
        super().save(*args, **kwargs)


class HistorialDocumento(models.Model):
    """Bitácora append-only de cada documento."""

    class Accion(models.TextChoices):
        CREADO = "creado", "Creado"
        EDITADO = "editado", "Editado"
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
