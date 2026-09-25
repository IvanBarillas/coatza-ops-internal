from ..integracion import dependencias_autorizadas
from ..models import Bien, Dictamen, Direccion
from .services import CLASES_DE_SOPORTE

APP_SLUG = "seguimientos_oficios"


def direcciones_con_soporte(request, permiso="can_view_support"):
    """Direcciones con soporte técnico habilitado que el usuario puede ver (alcance por dependencia)."""
    base = Direccion.objects.filter(is_active=True, is_deleted=False, soporte_habilitado=True)
    if request.axentra_is_root:
        return base
    ids = dependencias_autorizadas(request.user, app_slug=APP_SLUG, permiso=permiso)
    return base.filter(dependencia_uuid__in=ids)


def dictamenes_visibles(request):
    return (
        Dictamen.objects.filter(
            is_deleted=False, documento__clase__in=CLASES_DE_SOPORTE,
            documento__direccion__in=direcciones_con_soporte(request),
        )
        .select_related("documento", "documento__direccion")
        .prefetch_related("equipos")
    )


def bienes_catalogo(request, permiso="can_manage_support"):
    """Bienes de catálogo que un dictamen puede amparar (no dados de baja)."""
    return (
        Bien.objects.filter(is_deleted=False, direccion__in=direcciones_con_soporte(request, permiso))
        .exclude(estado=Bien.Estado.BAJA).select_related("direccion").order_by("nombre", "identificador")
    )
