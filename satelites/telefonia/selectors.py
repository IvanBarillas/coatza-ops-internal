from django.core.paginator import Paginator
from django.db.models import Q

from .integracion import valor_entorno
from .models import Linea, Reporte

APP_SLUG = "telefonia"

TABS = (
    ("pendientes", "Pendientes", (Reporte.Estatus.PENDIENTE,)),
    ("atendidos", "Atendidos", (Reporte.Estatus.ATENDIDO,)),
    ("cancelados", "Cancelados", (Reporte.Estatus.CANCELADO,)),
    ("todos", "Todos", None),
)


def permitido(request, llave):
    return request.axentra_is_root or llave in request.axentra_permissions_list


def semaforo_umbrales():
    return int(valor_entorno("TEL_SEMAFORO_AMBAR", "3")), int(valor_entorno("TEL_SEMAFORO_ROJO", "7"))


def color_semaforo(dias):
    ambar, rojo = semaforo_umbrales()
    return "rojo" if dias >= rojo else "ambar" if dias >= ambar else "verde"


def reportes_visibles(request):
    return Reporte.objects.filter(is_deleted=False).select_related("linea")


def reportes_propios(request):
    return reportes_visibles(request).filter(responsable=request.user)


def lineas_visibles(request):
    return Linea.objects.filter(is_deleted=False)


def buscar_reportes(queryset, consulta):
    for termino in (consulta or "").split()[:6]:
        queryset = queryset.filter(
            Q(folio__icontains=termino) | Q(linea_texto__icontains=termino) | Q(sitio_texto__icontains=termino)
            | Q(contacto_nombre__icontains=termino) | Q(detalle__icontains=termino)
        )
    return queryset


def buscar_lineas(queryset, consulta):
    for termino in (consulta or "").split()[:6]:
        queryset = queryset.filter(
            Q(identificador__icontains=termino) | Q(sitio__icontains=termino) | Q(direccion__icontains=termino)
            | Q(municipio__icontains=termino)
        )
    return queryset


def aplicar_tab(queryset, tab):
    estatus = {clave: e for clave, _, e in TABS}[tab]
    queryset = queryset.filter(estatus__in=estatus) if estatus else queryset
    return queryset.order_by("levantado", "created_at") if tab == "pendientes" else queryset


def tab_valida(valor):
    return valor if valor in {c for c, _, _ in TABS} else "pendientes"


def pagina(items, numero, por_pagina=25):
    return Paginator(items, por_pagina).get_page(numero)
