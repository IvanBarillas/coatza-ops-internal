import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class BaseEventos(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField("Creado", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        abstract = True


class Evento(BaseEventos):
    class Estatus(models.TextChoices):
        PROGRAMADO = "programado", "Programado"
        EN_CURSO = "en_curso", "En curso"
        CONCLUIDO = "concluido", "Concluido"
        CANCELADO = "cancelado", "Cancelado"

    nombre = models.CharField("Evento", max_length=200)
    lugar = models.CharField("Lugar", max_length=200)
    inicio = models.DateTimeField("Inicio", db_index=True)
    fin = models.DateTimeField("Fin")
    descripcion = models.TextField("Qué se cubre", blank=True)
    ticket = models.CharField("Ticket", max_length=60, blank=True, help_text="Folio del ticket del que nació el evento, si lo hay.")
    estatus = models.CharField("Estado", max_length=12, choices=Estatus.choices, default=Estatus.PROGRAMADO, db_index=True)
    motivo_cancelacion = models.TextField("Motivo de cancelación", blank=True)
    notas_cierre = models.TextField("Notas de cierre", blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        db_table = "evt_evento"
        ordering = ["inicio"]
        constraints = [models.CheckConstraint(condition=Q(fin__gt=F("inicio")), name="evt_evento_fin_despues_de_inicio")]

    def __str__(self):
        return self.nombre

    @property
    def abierto(self):
        return self.estatus in (self.Estatus.PROGRAMADO, self.Estatus.EN_CURSO)


class Asignacion(BaseEventos):
    """Un técnico en un tramo de horas del evento. Una persona puede tener varios tramos y un evento varios técnicos."""

    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="asignaciones")
    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    tecnico_nombre = models.CharField(max_length=200)
    desde = models.DateTimeField("Desde")
    hasta = models.DateTimeField("Hasta")
    nota = models.CharField("Nota", max_length=200, blank=True)

    class Meta:
        db_table = "evt_asignacion"
        ordering = ["desde", "tecnico_nombre"]
        constraints = [models.CheckConstraint(condition=Q(hasta__gt=F("desde")), name="evt_asignacion_hasta_despues_de_desde")]


class ValeSalida(BaseEventos):
    """Referencia a un vale de salida: UUID y etiqueta (snapshot) si se eligió del satélite de préstamos, o texto libre; sin ForeignKey."""

    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="vales")
    referencia = models.CharField("Vale (número o UUID)", max_length=80)
    ref_id = models.UUIDField("Vale elegido del sistema", null=True, blank=True, help_text="UUID del vale cuando se eligió del satélite de préstamos.")
    etiqueta = models.CharField("Vale (texto al vincular)", max_length=200, blank=True)
    nota = models.CharField("Qué se lleva", max_length=200, blank=True)

    class Meta:
        db_table = "evt_vale"
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["evento", "referencia"], name="evt_vale_unico_por_evento")]


class TramiteLinea(BaseEventos):
    """Reubicación o contratación de líneas telefónicas para el evento (texto libre; no depende del satélite de telefonía)."""

    class Tipo(models.TextChoices):
        REUBICACION = "reubicacion", "Reubicar una línea"
        NUEVA = "nueva", "Contratar línea nueva"
        OTRO = "otro", "Otro"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        EN_TRAMITE = "en_tramite", "En trámite"
        LISTO = "listo", "Listo"

    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="tramites")
    tipo = models.CharField("Trámite", max_length=12, choices=Tipo.choices, default=Tipo.REUBICACION)
    descripcion = models.CharField("Descripción", max_length=250)
    referencia = models.CharField("Línea o enlace", max_length=120, blank=True)
    estado = models.CharField("Estado", max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)

    class Meta:
        db_table = "evt_tramite_linea"
        ordering = ["created_at"]


class Bitacora(BaseEventos):
    """Notas y movimientos del evento; solo se agregan."""

    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="bitacora")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    usuario_nombre = models.CharField(max_length=200, blank=True)
    accion = models.CharField(max_length=30, db_index=True)
    detalle = models.TextField(blank=True)

    class Meta:
        db_table = "evt_bitacora"
        ordering = ["-created_at"]
