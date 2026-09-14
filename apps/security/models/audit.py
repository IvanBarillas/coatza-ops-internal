# apps/security/models/audit.py
import uuid
from django.db import models
from django.conf import settings

class SecurityAuditLog(models.Model):
    """Caja Negra Forense Global de Axentra OS con Catálogo de Acciones Normalizado."""
    class Levels(models.TextChoices):
        CRITICAL = "CRITICAL", "🚨 Operación Crítica / Traslape / Bloqueo"
        SUCCESS = "SUCCESS", "🟢 Operación Exitosa / Acceso Concedido"
        INFO = "INFO", "🔵 Modificación Informativa / Rutina"

    class ActionTypes(models.TextChoices):
        CREATE = "CREATE", "➕ ALTA / CREACIÓN"
        UPDATE = "UPDATE", "📝 MODIFICACIÓN / ACTUALIZACIÓN"
        DELETE = "DELETE", "❌ BAJA / ELIMINACIÓN"
        ASSIGN = "ASSIGN", "🔑 ASIGNACIÓN / PRIVILEGIO"
        ACCESS = "ACCESS", "🔓 ACCESO / LOGIN / CONTROL"
        QUERY  = "QUERY",  "🔍 CONSULTA / EXTRACCIÓN FORENSE"
        RESET  = "RESET",  "🔒 RESTABLECIMIENTO / LOCKDOWN"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    correlation_id = models.UUIDField(null=True, blank=True, db_index=True, editable=False)
    system_actor = models.CharField(max_length=100, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    app_namespace = models.CharField("Ecosistema / App", max_length=50, default="core", db_index=True)
    action_type = models.CharField("Tipo de Acción (Verbo)", max_length=20, choices=ActionTypes.choices, default=ActionTypes.UPDATE, db_index=True)
    module_component = models.CharField("Componente / Vista de Origen", max_length=100, default="GENERAL", db_index=True)
    level_status = models.CharField("Nivel del Evento", max_length=15, choices=Levels.choices, default=Levels.INFO, db_index=True)
    action_name = models.CharField("Descripción de la Acción", max_length=150, db_index=True)
    search_target = models.CharField("Criterio / Llave de Búsqueda Dinámica", max_length=255, null=True, blank=True, db_index=True)
    target_scope = models.CharField("Ámbito / Descripción del Destino", max_length=255)
    operator_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='logs', verbose_name="Operador")
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='auditorias_recibidas')
    ip_address = models.GenericIPAddressField("Dirección IP", default="127.0.0.1", db_index=True)
    user_agent = models.TextField("Navegador / Dispositivo", null=True, blank=True)
    payload_json = models.JSONField("Telemetría Estructurada JSON", default=dict, blank=True)

    class Meta:
        db_table = 'axentra_sec_audit_logs'
        verbose_name = "Log de Auditoría"
        verbose_name_plural = "Logs de Auditoría"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        from apps.security.services.audit_context import current_audit, mark_audit_failure, redact_payload
        if not self._state.adding:
            raise ValidationError('Los eventos de auditoría no se editan; registrar un evento correctivo.')
        context = current_audit.get()
        if self.correlation_id is None and context:
            self.correlation_id = context['id']
        if self.operator_user_id is None and not self.system_actor.strip():
            mark_audit_failure()
            raise ValidationError('Un evento requiere usuario o actor de sistema identificado.')
        self.payload_json = redact_payload(self.payload_json)
        try:
            return super().save(*args, **kwargs)
        except Exception:
            mark_audit_failure()
            raise

    def __str__(self):
        return f"[{self.app_namespace.upper()}] [{self.action_type}] - {self.operator_user.email if self.operator_user_id else self.system_actor}"
    
