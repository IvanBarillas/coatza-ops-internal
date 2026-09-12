# apps/shared/dependency_capabilities.py

import logging

try:
    from apps.security.models.organigrama import AppDependencyCapability
except ImportError:
    from apps.security.models import AppDependencyCapability

logger = logging.getLogger("axentra.security")


class AxentraCapabilityOrchestrator:
    """
    Orquestador maestro de capacidades departamentales de Axentra OS.

    Evalúa qué facultades tiene la dependencia del usuario dentro de una app.

    Modelo actual:
    - can_operate
    - can_supervise
    - can_authorize

    Compatibilidad temporal:
    - es_alfa  -> can_operate
    - es_beta  -> can_supervise
    - es_hibrido -> dos o más capacidades activas
    """

    @staticmethod
    def _normalizar_app_slug(app_slug) -> str:
        if hasattr(app_slug, "value"):
            return str(app_slug.value).strip().lower()
        return str(app_slug).strip().lower()

    @staticmethod
    def _resolver_perfil(user):
        return (
            getattr(user, "axentra_profile", None)
            or getattr(user, "funcionario_profile", None)
        )

    @staticmethod
    def _resolver_area(perfil):
        if not perfil or not perfil.is_active or perfil.is_deleted:
            return None
        return (
            getattr(perfil, "area", None)
            or getattr(perfil, "area_operativa", None)
        )

    @staticmethod
    def _usuario_dado_de_baja(user) -> bool:
        return bool(getattr(user, "is_deleted", False) or not user.is_active)

    @staticmethod
    def obtener_estatus_capacidad(user, app_slug: str) -> dict:
        """
        Analiza el árbol orgánico del usuario y dictamina sus capacidades
        departamentales para una app.

        Retorna una estructura estable para vistas, servicios y templates.
        """
        app_slug = AxentraCapabilityOrchestrator._normalizar_app_slug(app_slug)

        resultado = {
            "tiene_acceso": False,
            "can_operate": False,
            "can_supervise": False,
            "can_authorize": False,
            "es_alfa": False,
            "es_beta": False,
            "es_hibrido": False,
            "dependencia": None,
            "capacidad": None,
            "app_slug": app_slug,
            "error_codigo": None,
        }

        if not user or not user.is_authenticated:
            resultado["error_codigo"] = "ANONYMOUS_USER"
            return resultado

        if AxentraCapabilityOrchestrator._usuario_dado_de_baja(user):
            resultado["error_codigo"] = "USER_SOFT_DELETED"
            return resultado

        perfil = AxentraCapabilityOrchestrator._resolver_perfil(user)
        if not perfil or not perfil.is_active or perfil.is_deleted:
            resultado["error_codigo"] = "MISSING_PROFILE"
            return resultado

        area = AxentraCapabilityOrchestrator._resolver_area(perfil)
        if not area or not getattr(area, "dependencia", None):
            resultado["error_codigo"] = "MISSING_ORGANIZATION_NODE"
            return resultado

        dependencia = area.dependencia
        if not area.is_active or area.is_deleted or not dependencia.is_active or dependencia.is_deleted:
            resultado['error_codigo'] = 'INACTIVE_ORGANIZATION_NODE'
            return resultado
        resultado["dependencia"] = dependencia

        try:
            capacidad = (
                AppDependencyCapability.objects
                .select_related("app", "dependencia")
                .get(
                    dependencia=dependencia,
                    app__slug=app_slug,
                    app__is_active=True,
                    app__is_deleted=False,
                    is_active=True,
                    is_deleted=False,
                )
            )
        except AppDependencyCapability.DoesNotExist:
            resultado["error_codigo"] = f"NO_CAPABILITY_REGISTERED_FOR_{app_slug.upper()}"
            return resultado
        except AppDependencyCapability.MultipleObjectsReturned:
            logger.error(
                "Capacidades duplicadas detectadas para dependencia=%s app=%s",
                dependencia.id,
                app_slug,
            )
            resultado["error_codigo"] = "DUPLICATED_CAPABILITY_MATRIX"
            return resultado

        resultado["capacidad"] = capacidad
        resultado["can_operate"] = bool(capacidad.can_operate)
        resultado["can_supervise"] = bool(capacidad.can_supervise)
        resultado["can_authorize"] = bool(capacidad.can_authorize)

        capacidades_activas = [
            resultado["can_operate"],
            resultado["can_supervise"],
            resultado["can_authorize"],
        ]

        resultado["tiene_acceso"] = any(capacidades_activas)
        resultado["es_hibrido"] = sum(1 for valor in capacidades_activas if valor) >= 2

        # Compatibilidad temporal con lógica anterior alfa/beta.
        resultado["es_alfa"] = resultado["can_operate"]
        resultado["es_beta"] = resultado["can_supervise"]

        if not resultado["tiene_acceso"]:
            resultado["error_codigo"] = "CAPABILITIES_DISABLED"

        return resultado

    @staticmethod
    def dependencia_puede_operar(user, app_slug: str) -> bool:
        return AxentraCapabilityOrchestrator.obtener_estatus_capacidad(
            user,
            app_slug,
        ).get("can_operate", False)

    @staticmethod
    def dependencia_puede_supervisar(user, app_slug: str) -> bool:
        return AxentraCapabilityOrchestrator.obtener_estatus_capacidad(
            user,
            app_slug,
        ).get("can_supervise", False)

    @staticmethod
    def dependencia_puede_autorizar(user, app_slug: str) -> bool:
        return AxentraCapabilityOrchestrator.obtener_estatus_capacidad(
            user,
            app_slug,
        ).get("can_authorize", False)