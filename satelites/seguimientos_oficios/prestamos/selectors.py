from ..integracion import dependencias_autorizadas
from ..models import Bien, Direccion, Prestamo

APP_SLUG = "seguimientos_oficios"


def direcciones_con_vales(request, permiso="can_view_loans"):
    """Direcciones con vales habilitados que el usuario puede ver (alcance por dependencia)."""
    base = Direccion.objects.filter(is_active=True, is_deleted=False, vales_habilitados=True)
    if request.axentra_is_root:
        return base
    ids = dependencias_autorizadas(request.user, app_slug=APP_SLUG, permiso=permiso)
    return base.filter(dependencia_uuid__in=ids)


def bienes_visibles(request):
    return Bien.objects.filter(is_deleted=False, direccion__in=direcciones_con_vales(request)).select_related("direccion")


def bienes_disponibles(request):
    """Bienes que hoy se pueden prestar: disponibles y sin un préstamo abierto."""
    return bienes_visibles(request).filter(is_active=True, estado=Bien.Estado.DISPONIBLE).exclude(asignaciones__abierto=True)


def prestamos_visibles(request, permiso="can_view_loans"):
    return (
        Prestamo.objects.filter(is_deleted=False, documento__direccion__in=direcciones_con_vales(request, permiso))
        .select_related("documento", "documento__direccion", "documento__gestor")
        .prefetch_related("renglones__bien")
    )
