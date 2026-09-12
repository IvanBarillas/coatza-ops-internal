# apps/security/selectors/security_selectors.py
import logging
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Q
from datetime import timedelta

from apps.security.models.organigrama import AppDependencyCapability, Dependencia
from apps.shared.apps_config import AppIdentifier
from apps.security.models import SecurityAuditLog, UserAppRole, AppModule
from apps.shared.manifest_registry import AxentraOSRegistry

User = get_user_model()
logger = logging.getLogger(__name__)

class SecurityDashboardSelectors:
    """Métricas y buffers forenses en caliente para la Consola Analítica."""

    @classmethod
    def obtener_metricas_firewall(cls) -> dict:
        return {
            "total_apps": AppModule.objects.filter(is_active=True, is_deleted=False).count(),
            "llaves_activas_db": UserAppRole.objects.filter(
                is_active=True, is_deleted=False,
                user__is_active=True, user__is_deleted=False,
                app__is_active=True, app__is_deleted=False,
            ).count(),
            "cuentas_riesgo": User.objects.filter(
                Q(is_active=False) | Q(is_deleted=True),
                roles__is_active=True, roles__is_deleted=False,
                roles__app__is_active=True, roles__app__is_deleted=False,
            ).distinct().count(),
        }

    @classmethod
    def obtener_buffer_auditoria(cls, limite: int = 50, filtros: dict = None) -> list:
        """
        Obtiene el buffer reciente de auditoría forense.

        Regla operativa:
        - Si el usuario manda fecha_inicio o fecha_fin, respeta el rango.
        - Si no manda fechas, muestra las últimas 24 horas.
        - Aplica filtros por app, acción, severidad, target y operador.
        """

        filtros = filtros or {}

        query = Q()

        fecha_inicio = filtros.get("fecha_inicio")
        fecha_fin = filtros.get("fecha_fin")

        if fecha_inicio or fecha_fin:
            if fecha_inicio:
                query &= Q(created_at__date__gte=fecha_inicio)

            if fecha_fin:
                query &= Q(created_at__date__lte=fecha_fin)

        else:
            hace_24_horas = timezone.now() - timedelta(hours=24)
            query &= Q(created_at__gte=hace_24_horas)

        app_namespace = filtros.get("app_namespace")
        action_type = filtros.get("action_type")
        level_status = filtros.get("level_status")
        search_target = filtros.get("search_target")
        operador = filtros.get("operador")

        if app_namespace:
            query &= Q(
                app_namespace=str(app_namespace).strip().lower(),
            )

        if action_type:
            query &= Q(
                action_type=str(action_type).strip().upper(),
            )

        if level_status:
            query &= Q(
                level_status=str(level_status).strip().upper(),
            )

        if search_target:
            query &= Q(
                search_target__icontains=str(search_target).strip(),
            )

        if operador:
            query &= Q(
                operator_user__email__icontains=str(operador).strip().lower(),
            )

        logs_queryset = (
            SecurityAuditLog.objects
            .filter(query)
            .select_related("operator_user")
            .order_by("-created_at")[:limite]
        )

        return [
            {
                "timestamp": log.created_at,
                "tipo": log.level_status or "INFO",
                "app": str(log.app_namespace or "core").upper(),
                "verbo": log.action_type or "--",
                "operador": log.operator_user.email if log.operator_user else "SISTEMA",
                "accion": log.action_name or "--",
                "target": log.search_target or "--",
                "destino": log.target_scope or "--",
            }
            for log in logs_queryset
        ]
    

class CapabilitySelectors:
    @classmethod
    def obtener_labels_manifiesto(cls, app_slug: str) -> dict:
        """
        Obtiene etiquetas semánticas de capacidades desde el manifiesto de la app.

        Si la app no define CAPABILITIES, usa labels base.
        """

        manifiesto = AxentraOSRegistry.get_manifest_by_slug(
            app_slug,
        )

        capacidades = (
            getattr(manifiesto, "CAPABILITIES", {}) or {}
            if manifiesto
            else {}
        )

        return {
            "can_operate": capacidades.get(
                "can_operate",
                {
                    "label": "Puede Operar",
                    "help_text": "Permite que esta dependencia ejecute procesos operativos dentro del módulo.",
                },
            ),
            "can_supervise": capacidades.get(
                "can_supervise",
                {
                    "label": "Puede Supervisar",
                    "help_text": "Permite que esta dependencia supervise información, estados o expedientes del módulo.",
                },
            ),
            "can_authorize": capacidades.get(
                "can_authorize",
                {
                    "label": "Puede Autorizar",
                    "help_text": "Permite que esta dependencia autorice decisiones críticas o cierres dentro del módulo.",
                },
            ),
        }

    @classmethod
    def obtener_matriz_capacidades_contexto(cls, app_activa: AppModule) -> dict:
        """
        Compila el contexto de capacidades para una aplicación.

        Devuelve:
        - matriz: dependencias ya vinculadas a la app.
        - dependencias_disponibles: dependencias activas todavía no vinculadas.
        - labels: etiquetas semánticas para can_operate, can_supervise y can_authorize.
        """

        capacidades_reales = (
            AppDependencyCapability.objects
            .filter(
                app=app_activa,
                dependencia__is_active=True,
                dependencia__is_deleted=False,
            )
            .select_related(
                "dependencia",
            )
            .order_by(
                "dependencia__nombre",
            )
        )

        deps_ya_vinculadas = capacidades_reales.values_list(
            "dependencia_id",
            flat=True,
        )

        dependencias_disponibles = (
            Dependencia.objects
            .filter(
                is_active=True,
                is_deleted=False,
            )
            .exclude(
                id__in=deps_ya_vinculadas,
            )
            .order_by(
                "nombre",
            )
        )

        return {
            "matriz": capacidades_reales,
            "dependencias_disponibles": dependencias_disponibles,
            "labels": cls.obtener_labels_manifiesto(
                app_activa.slug,
            ),
        }