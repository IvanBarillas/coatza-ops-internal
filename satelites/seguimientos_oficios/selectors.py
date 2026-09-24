from .integracion import dependencias_autorizadas
from .models import Direccion, Documento

APP_SLUG = "seguimientos_oficios"


def direcciones_visibles(request):
    base = Direccion.objects.filter(is_active=True, is_deleted=False)
    if request.axentra_is_root:
        return base
    ids = dependencias_autorizadas(request.user, app_slug=APP_SLUG, permiso="can_view_oficios")
    return base.filter(dependencia_uuid__in=ids)


def documentos_visibles(request):
    return Documento.objects.filter(
        is_deleted=False, direccion__in=direcciones_visibles(request)
    ).select_related("direccion")


def documento_visible(request, pk):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(documentos_visibles(request), pk=pk)
