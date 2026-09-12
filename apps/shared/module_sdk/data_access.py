"""Alcance por dependencia: filtrar antes de listar, exportar o buscar por PK.

La política y los nombres de campos provienen de código confiable del satélite,
jamás de parámetros HTTP. No concede permisos funcionales ni herencia jerárquica.
"""
from django.db.models import Q, Subquery
from django.utils import timezone


def authorized_departments(user, *, app_slug, permission):
    from apps.security.models import Dependencia, DepartmentAccessGrant, UserAppRole, UserProfile
    from apps.security.services.permission_loader import get_app_permissions
    from .services import get_module_runtime_status

    denied = Dependencia.objects.none()
    if not user or not user.is_authenticated or not user.is_active or user.is_deleted:
        return denied
    config = get_app_permissions(app_slug)
    if not permission or permission == 'has_access_module' or permission not in config['permissions']:
        return denied
    runtime = get_module_runtime_status(app_slug)
    if runtime is None or not runtime.available:
        return denied
    membership = UserAppRole.objects.filter(
        user=user, app__slug=app_slug, app__is_active=True, app__is_deleted=False,
        is_active=True, is_deleted=False,
    ).first()
    if membership is None:
        return denied
    permissions = set(membership.permissions_list or [])
    if membership.role == 'owner':
        permissions.update(config['roles'].get('owner', []))
    if permission not in permissions and f'{app_slug}__{permission}' not in permissions:
        return denied
    profile = UserProfile.objects.filter(
        user=user, is_active=True, is_deleted=False,
        area__is_active=True, area__is_deleted=False,
        area__dependencia__is_active=True, area__dependencia__is_deleted=False,
    ).values('area__dependencia_id').first()
    if not profile:
        return denied
    department_id = profile['area__dependencia_id']
    grants = DepartmentAccessGrant.objects.filter(
        membership=membership, source_department_id=department_id,
        permission=permission, is_active=True, is_deleted=False,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
    return Dependencia.objects.filter(is_active=True, is_deleted=False).filter(
        Q(pk=department_id) | Q(pk__in=Subquery(grants.values('target_department_id')))
    )


def scope_queryset(queryset, user, *, app_slug, permission, department_field='dependencia'):
    """Devuelve un QuerySet limitado; PK ajena debe buscarse sobre este resultado.

    Para altas/cambios de adscripción, validar también la dependencia de destino
    contra authorized_departments dentro de la transacción de la operación.
    """
    departments = authorized_departments(user, app_slug=app_slug, permission=permission)
    return queryset.filter(**{f'{department_field}__in': departments})
