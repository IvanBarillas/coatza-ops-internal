from django.db import connection
from django.db.models import Count, Q

from .integracion import dependencias_autorizadas
from .models import AdjuntoOCR, Direccion, Documento

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


def _coincidencias_ocr(termino):
    if connection.vendor == "postgresql":
        from django.contrib.postgres.search import SearchQuery, SearchVector

        return (
            AdjuntoOCR.objects.annotate(vector=SearchVector("texto", config="spanish"))
            .filter(vector=SearchQuery(termino, config="spanish", search_type="websearch"))
        )
    return AdjuntoOCR.objects.filter(texto__icontains=termino)


def buscar_documentos(queryset, filtros):
    """Aplica los filtros ya validados (dict limpio de FiltroDocumentosForm)."""
    for campo in ("sentido", "clase", "estado", "direccion"):
        if filtros.get(campo):
            queryset = queryset.filter(**{campo: filtros[campo]})
    if filtros.get("gestor") == "sin":
        queryset = queryset.filter(gestor__isnull=True)
    elif filtros.get("gestor"):
        queryset = queryset.filter(gestor_id=filtros["gestor"])
    if filtros.get("desde"):
        queryset = queryset.filter(fecha__gte=filtros["desde"])
    if filtros.get("hasta"):
        queryset = queryset.filter(fecha__lte=filtros["hasta"])
    for termino in (filtros.get("q") or "").split():
        en_ocr = _coincidencias_ocr(termino).values("adjunto__documento_id")
        queryset = queryset.filter(
            Q(folio__icontains=termino) | Q(asunto__icontains=termino)
            | Q(contraparte__icontains=termino) | Q(director_nombre__icontains=termino)
            | Q(pk__in=en_ocr)
        )
    return queryset


TABS = (
    ("pendientes", "Pendientes", (Documento.Estado.GENERADO, Documento.Estado.ENTREGADO)),
    ("concluidos", "Concluidos", (Documento.Estado.CONCLUIDO, Documento.Estado.REGISTRADO)),
    ("cancelados", "Cancelados", (Documento.Estado.CANCELADO,)),
    ("todos", "Todos", None),
)


def tab_activa(valor, hay_texto):
    if valor in {clave for clave, _, _ in TABS}:
        return valor
    return "todos" if hay_texto else "pendientes"


def aplicar_tab(queryset, tab):
    estados = {clave: e for clave, _, e in TABS}[tab]
    queryset = queryset.filter(estado__in=estados) if estados else queryset
    return queryset.order_by("created_at") if tab == "pendientes" else queryset


def conteos_tabs(queryset):
    agregados = {
        clave: Count("pk", filter=Q(estado__in=estados) if estados else Q())
        for clave, _, estados in TABS
    }
    return queryset.order_by().aggregate(**agregados)


def resumen_gestores(queryset):
    """Pendientes agrupados por gestor: [(gestor_id | None, nombre, total)]."""
    filas = (
        queryset.order_by().filter(estado__in=dict((c, e) for c, _, e in TABS)["pendientes"], sentido="enviado")
        .values("gestor_id", "gestor__nombre").annotate(total=Count("pk")).order_by("-total", "gestor__nombre")
    )
    return [(f["gestor_id"], f["gestor__nombre"] or "Sin gestor", f["total"]) for f in filas]


def gestores_visibles(request):
    from .models import Gestor

    return Gestor.objects.filter(
        is_active=True, is_deleted=False, direccion__in=direcciones_visibles(request)
    ).select_related("direccion")
