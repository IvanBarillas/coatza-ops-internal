# apps/security/utils/forensic_auditor.py
import logging
from apps.security.models.audit import SecurityAuditLog

logger = logging.getLogger(__name__)

class ForensicAuditor:
    
    @staticmethod
    def registrar_evento(request, action_type, module_component, action_name, target_scope, app_name=None, level=SecurityAuditLog.Levels.INFO, target_user=None, search_target=None, payload=None):
        """
        🚀 GUARDIÁN FORENSE EVOLUCIONADO: Normaliza la telemetría separando 
        el Verbo (action_type) del Sujeto/Componente (module_component).
        """
        try:
            from apps.security.middleware.sessions import client_ip
            ip = client_ip(request) or '127.0.0.1'
            user_agent = request.META.get('HTTP_USER_AGENT', 'Desconocido/API')[:500]

            if not app_name and getattr(request, 'resolver_match', None):
                app_name = request.resolver_match.app_name

            # Creación física indexada en Postgres
            return SecurityAuditLog.objects.create(
                app_namespace=app_name.lower() if app_name else "core",
                action_type=action_type,                  # ◄── 'CREATE', 'UPDATE', etc.
                module_component=str(module_component).upper().strip(),  # ◄── 'ALTA_USUARIOS', 'MATRIZ'
                level_status=level,
                action_name=action_name,
                search_target=str(search_target).strip() if search_target else None,
                target_scope=target_scope,
                operator_user=request.user,
                target_user=target_user,
                ip_address=ip,
                user_agent=user_agent,
                payload_json=payload or {}
            )
        except Exception:
            from apps.security.services.audit_context import AuditWriteError, mark_audit_failure
            mark_audit_failure()
            logger.error('AUDIT_WRITE_FAILED: no se pudo persistir la evidencia.')
            raise AuditWriteError('No se pudo persistir la evidencia de auditoría.') from None