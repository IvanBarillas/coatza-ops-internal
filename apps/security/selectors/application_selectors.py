"""Alcance y métricas de gobierno; no sustituyen permisos finos del módulo."""
from django.db.models import Count, Q

from apps.security.models import AppModule, UserAppRole


class ApplicationGovernanceSelectors:
    @staticmethod
    def scope(user):
        apps = AppModule.objects.filter(is_active=True, is_deleted=False)
        if not user.is_authenticated or not user.is_active or user.is_deleted:
            return apps.none()
        if user.is_superuser or user.is_manager:
            return apps
        memberships = UserAppRole.objects.filter(
            user=user, role="owner", is_active=True, is_deleted=False,
        ).values("app_id")
        return apps.filter(pk__in=memberships)

    @staticmethod
    def with_counts(apps):
        valid = Q(
            roles__is_active=True, roles__is_deleted=False,
            roles__user__is_active=True, roles__user__is_deleted=False,
        )
        return apps.annotate(
            total_usuarios=Count("roles__user", filter=valid, distinct=True),
            total_owners=Count("roles__user", filter=valid & Q(roles__role="owner"), distinct=True),
            total_operadores=Count("roles__user", filter=valid & ~Q(roles__role="owner"), distinct=True),
        )

    @classmethod
    def overview(cls, user):
        apps = cls.scope(user)
        counts = cls.with_counts(apps)
        roles = UserAppRole.objects.filter(
            app__in=apps, is_deleted=False,
            user__is_active=True, user__is_deleted=False,
        )
        totals = roles.aggregate(
            total_usuarios_con_acceso=Count("user", filter=Q(is_active=True), distinct=True),
            total_owners=Count("pk", filter=Q(is_active=True, role="owner")),
            total_roles_suspendidos=Count("pk", filter=Q(is_active=False)),
        )
        totals.update(
            total_apps_gobernadas=apps.count(),
            total_apps_sin_owner=counts.filter(total_owners=0).count(),
            # Primero sin responsable, luego nombre; nunca más de cinco filas.
            resumen_apps=list(counts.order_by("total_owners", "name", "pk")[:5]),
        )
        return totals
