import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class BasePermisos(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField("Creado", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        abstract = True


class Tipo(models.TextChoices):
    SINDICALIZADO = "sindicalizado", "Sindicalizado"
    CONFIANZA = "confianza", "Confianza"


class Configuracion(models.Model):
    """Ajustes globales (una sola fila): días económicos de cada periodo, iguales para todo el personal sindicalizado."""

    dias_economicos_p1 = models.PositiveSmallIntegerField("Días económicos del 1.er periodo (enero a junio)", default=1)
    dias_economicos_p2 = models.PositiveSmallIntegerField("Días económicos del 2.º periodo (julio a diciembre)", default=1)

    class Meta:
        db_table = "perm_configuracion"
        verbose_name = "Configuración"

    @classmethod
    def obtener(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def dias_economicos(self, periodo):
        return self.dias_economicos_p1 if periodo == 1 else self.dias_economicos_p2


class RangoAntiguedad(BasePermisos):
    """Fila de la tabla de vacaciones: a partir de cuántos años de antigüedad, cuántos días tiene cada periodo."""

    tipo = models.CharField("Tipo de personal", max_length=15, choices=Tipo.choices)
    desde_anios = models.PositiveSmallIntegerField("Desde (años de antigüedad)")
    dias_p1 = models.PositiveSmallIntegerField("Días del 1.er periodo")
    dias_p2 = models.PositiveSmallIntegerField("Días del 2.º periodo")

    class Meta:
        db_table = "perm_rango_antiguedad"
        ordering = ["tipo", "desde_anios"]
        constraints = [models.UniqueConstraint(fields=["tipo", "desde_anios"], name="perm_rango_unico")]

    def __str__(self):
        return f"{self.get_tipo_display()} desde {self.desde_anios} años: {self.dias_p1}/{self.dias_p2}"

    def dias(self, periodo):
        return self.dias_p1 if periodo == 1 else self.dias_p2


class UmbralSede(BasePermisos):
    """Mínimo de personal que debe haber presente en una sede (según cuánta gente atiende)."""

    sede_uuid = models.UUIDField("Sede del Core", unique=True)
    sede_nombre = models.CharField("Sede", max_length=150)
    minimo = models.PositiveSmallIntegerField("Mínimo de personal presente", default=1)

    class Meta:
        db_table = "perm_umbral_sede"
        ordering = ["sede_nombre"]

    def __str__(self):
        return f"{self.sede_nombre}: mínimo {self.minimo}"


class Empleado(BasePermisos):
    """Persona con derecho a vacaciones (y, si es sindicalizada, a días económicos). Es un usuario del sistema."""

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="empleado_permisos")
    tipo = models.CharField("Tipo de personal", max_length=15, choices=Tipo.choices, default=Tipo.CONFIANZA)
    fecha_ingreso = models.DateField("Fecha de ingreso")
    sede_uuid = models.UUIDField("Sede del Core", null=True, blank=True, db_index=True)
    sede_nombre = models.CharField("Sede", max_length=150, blank=True)
    is_active = models.BooleanField("Activo", default=True)

    class Meta:
        db_table = "perm_empleado"
        ordering = ["usuario__first_name", "usuario__last_name"]

    def __str__(self):
        return getattr(self.usuario, "full_name", "") or self.usuario.email

    @property
    def nombre(self):
        return str(self)

    @property
    def es_sindicalizado(self):
        return self.tipo == Tipo.SINDICALIZADO


class AjusteDias(BasePermisos):
    """Días de vacaciones de un empleado en un periodo, cuando difieren de la tabla por antigüedad."""

    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name="ajustes")
    anio = models.PositiveSmallIntegerField("Año")
    periodo = models.PositiveSmallIntegerField("Periodo", choices=((1, "1.er periodo"), (2, "2.º periodo")))
    dias = models.PositiveSmallIntegerField("Días")

    class Meta:
        db_table = "perm_ajuste_dias"
        constraints = [models.UniqueConstraint(fields=["empleado", "anio", "periodo"], name="perm_ajuste_unico")]


class Solicitud(BasePermisos):
    """Solicitud de vacaciones o de días económicos. El saldo se descuenta al registrarla; «validado» es solo un control."""

    class TipoSolicitud(models.TextChoices):
        VACACIONES = "vacaciones", "Vacaciones"
        ECONOMICO = "economico", "Día económico"

    class Estatus(models.TextChoices):
        ACTIVA = "activa", "Activa"
        CANCELADA = "cancelada", "Cancelada"

    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name="solicitudes")
    tipo = models.CharField("Tipo", max_length=12, choices=TipoSolicitud.choices)
    anio = models.PositiveSmallIntegerField("Año")
    periodo = models.PositiveSmallIntegerField("Periodo", choices=((1, "1.er periodo"), (2, "2.º periodo")))
    fecha_inicio = models.DateField("Del")
    fecha_fin = models.DateField("Al")
    dias = models.PositiveSmallIntegerField("Días que descuenta")
    comentarios = models.TextField("Comentarios", blank=True)
    estatus = models.CharField("Estatus", max_length=10, choices=Estatus.choices, default=Estatus.ACTIVA, db_index=True)
    motivo_cancelacion = models.TextField(blank=True)
    validado = models.BooleanField("Validado", default=False, db_index=True)
    validado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    validado_en = models.DateTimeField(null=True, blank=True)
    sede_uuid = models.UUIDField(null=True, blank=True)
    sede_nombre = models.CharField(max_length=150, blank=True)
    bajo_umbral = models.JSONField("Días bajo el mínimo de la sede", default=list, blank=True)

    class Meta:
        db_table = "perm_solicitud"
        ordering = ["-fecha_inicio", "-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(fecha_fin__gte=models.F("fecha_inicio")), name="perm_fechas_validas"),
        ]

    def __str__(self):
        return f"{self.empleado} · {self.get_tipo_display()} {self.fecha_inicio:%d/%m/%Y}"

    @property
    def activa(self):
        return self.estatus == self.Estatus.ACTIVA

    def clean(self):
        if self.fecha_fin and self.fecha_inicio and self.fecha_fin < self.fecha_inicio:
            raise ValidationError("La fecha final no puede ser anterior a la inicial.")


class Movimiento(models.Model):
    """Bitácora de solicitudes y ajustes: solo se escribe."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    solicitud = models.ForeignKey(Solicitud, null=True, blank=True, on_delete=models.PROTECT, related_name="movimientos")
    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name="movimientos")
    accion = models.CharField(max_length=20)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    usuario_nombre = models.CharField(max_length=200, blank=True)
    texto = models.TextField(blank=True)
    datos = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "perm_movimiento"
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("La bitácora es de solo escritura.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("La bitácora no se puede borrar.")
