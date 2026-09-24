import uuid

from django.conf import settings
from django.db import models


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


class Documento(BaseOficios):
    class Tipo(models.TextChoices):
        RECIBIDO = "recibido", "Recibido"
        ENVIADO = "enviado", "Enviado"

    tipo = models.CharField("Tipo", max_length=10, choices=Tipo.choices)
    direccion = models.ForeignKey(
        Direccion, on_delete=models.PROTECT, related_name="documentos", verbose_name="Dirección"
    )
    contraparte = models.CharField(
        "Remitente o destinatario", max_length=200,
        help_text="Quién envía (recibidos) o a quién se dirige (enviados).",
    )
    director = models.CharField("Director", max_length=200, blank=True)
    asunto = models.CharField("Asunto", max_length=300)
    fecha = models.DateField("Fecha del oficio")
    folio = models.CharField("Folio", max_length=80, blank=True, db_index=True)
    archivo_hash = models.CharField("SHA-256", max_length=64, blank=True, db_index=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        db_table = "oficios_documento"
        ordering = ["-fecha", "-created_at"]
        verbose_name = "Oficio"
        verbose_name_plural = "Oficios"

    def __str__(self):
        return f"{self.folio or 's/f'} - {self.asunto[:60]}"
