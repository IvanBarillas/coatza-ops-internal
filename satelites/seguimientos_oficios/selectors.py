from collections import defaultdict

from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Q

from .integracion import dependencias_autorizadas, valor_entorno
from .models import Adjunto, AdjuntoOCR, Direccion, Documento
from .textos import coincidencias, terminos

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


def permitido(request, llave):
    return request.axentra_is_root or llave in request.axentra_permissions_list


PENDIENTES = (Documento.Estado.GENERADO, Documento.Estado.ENTREGADO)


def semaforo_umbrales():
    return int(valor_entorno("OFICIOS_SEMAFORO_AMBAR", "7")), int(valor_entorno("OFICIOS_SEMAFORO_ROJO", "15"))


def color_semaforo(dias):
    ambar, rojo = semaforo_umbrales()
    return "rojo" if dias >= rojo else "ambar" if dias >= ambar else "verde"


def documentos_seguimiento(request):
    """Enviados pendientes (Generado o Entregado) de las direcciones que el usuario puede seguir."""
    direcciones = Direccion.objects.filter(is_active=True, is_deleted=False)
    if not request.axentra_is_root:
        ids = dependencias_autorizadas(request.user, app_slug=APP_SLUG, permiso="can_view_tracking")
        direcciones = direcciones.filter(dependencia_uuid__in=ids)
    return Documento.objects.filter(
        is_deleted=False, sentido=Documento.Sentido.ENVIADO, estado__in=PENDIENTES, direccion__in=direcciones
    ).select_related("direccion", "gestor")


def documento_visible(request, pk):
    from django.http import Http404

    if permitido(request, "can_view_oficios"):
        documento = documentos_visibles(request).filter(pk=pk).first()
        if documento:
            return documento
    if permitido(request, "can_view_tracking"):
        documento = documentos_seguimiento(request).filter(pk=pk).first()
        if documento:
            return documento
    raise Http404("Documento no disponible.")


def _coincidencias_ocr(termino):
    """`termino` ya normalizado (minúsculas, sin acentos)."""
    if connection.vendor == "postgresql":
        from django.contrib.postgres.search import SearchQuery, SearchVector

        return (
            AdjuntoOCR.objects.filter(adjunto__eliminado=False, adjunto__rol__in=Adjunto.ROLES_CON_OCR)
            .annotate(vector=SearchVector("texto_normalizado", config="spanish"))
            .filter(vector=SearchQuery(termino, config="spanish", search_type="websearch"))
        )
    return AdjuntoOCR.objects.filter(
        adjunto__eliminado=False, adjunto__rol__in=Adjunto.ROLES_CON_OCR, texto_normalizado__contains=termino
    )


def buscar_documentos(queryset, filtros):
    """Aplica los filtros ya validados (dict limpio de FiltroDocumentosForm)."""
    for campo in ("sentido", "clase", "estado", "direccion"):
        if filtros.get(campo):
            queryset = queryset.filter(**{campo: filtros[campo]})
    if filtros.get("categoria") == "sin":
        queryset = queryset.filter(categoria__isnull=True)
    elif filtros.get("categoria"):
        queryset = queryset.filter(categoria_id=filtros["categoria"])
    if filtros.get("gestor") == "sin":
        queryset = queryset.filter(gestor__isnull=True)
    elif filtros.get("gestor"):
        queryset = queryset.filter(gestor_id=filtros["gestor"])
    if filtros.get("desde"):
        queryset = queryset.filter(fecha__gte=filtros["desde"])
    if filtros.get("hasta"):
        queryset = queryset.filter(fecha__lte=filtros["hasta"])
    return con_texto(queryset, filtros.get("q"))


def con_texto(queryset, consulta):
    """Documentos que contienen todos los términos, sin importar acentos ni mayúsculas, en sus datos o en el OCR."""
    for termino in terminos(consulta or ""):
        en_ocr = _coincidencias_ocr(termino).values("adjunto__documento_id")
        queryset = queryset.filter(Q(busqueda__contains=termino) | Q(pk__in=en_ocr))
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


def categorias_visibles(request):
    from .models import Categoria

    return Categoria.objects.filter(
        is_active=True, is_deleted=False, direccion__in=direcciones_visibles(request)
    ).select_related("direccion")


def buscar_con_coincidencias(request, consulta, pagina=None, por_pagina=15, filtros=None):
    """Documentos que contienen la consulta, con la página y el fragmento del OCR donde aparece."""
    documentos = buscar_documentos(documentos_visibles(request), {**(filtros or {}), "q": consulta})
    documentos = documentos.order_by("-fecha", "-created_at")
    paginador = Paginator(documentos, por_pagina).get_page(pagina)
    ids = [d.pk for d in paginador]
    encontrados = defaultdict(list)
    ocrs = AdjuntoOCR.objects.filter(adjunto__documento_id__in=ids, adjunto__eliminado=False,
        adjunto__rol__in=Adjunto.ROLES_CON_OCR, estado=AdjuntoOCR.Estado.LISTO).select_related("adjunto")
    for ocr in ocrs.order_by("adjunto__created_at"):
        for numero, fragmento in coincidencias(ocr.texto, ocr.texto_normalizado, consulta):
            encontrados[ocr.adjunto.documento_id].append({"adjunto": ocr.adjunto, "pagina": numero, "fragmento": fragmento})
    primeros = {}
    for adjunto in Adjunto.objects.filter(documento_id__in=ids, eliminado=False).order_by("-created_at"):
        primeros[adjunto.documento_id] = adjunto
    resultados = [
        {"documento": d, "coincidencias": encontrados[d.pk][:4], "primer_adjunto": primeros.get(d.pk)}
        for d in paginador
    ]
    return paginador, resultados
