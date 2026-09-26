from django.core.paginator import Paginator
from django.utils import timezone

from .models import Asignacion, Evento

APP_SLUG = "eventos"
ABIERTOS = (Evento.Estatus.PROGRAMADO, Evento.Estatus.EN_CURSO)


def permitido(request, llave):
    return request.axentra_is_root or llave in request.axentra_permissions_list


def eventos_todos():
    return Evento.objects.prefetch_related("asignaciones")


def asignaciones_de(usuario):
    return Asignacion.objects.filter(tecnico=usuario).select_related("evento")


def proximas_de(usuario):
    """Tramos del técnico en eventos abiertos que no han terminado; el más cercano primero."""
    return asignaciones_de(usuario).filter(evento__estatus__in=ABIERTOS, hasta__gte=timezone.now()).order_by("desde")


def recientes_de(usuario, limite=15):
    """Tramos ya pasados o de eventos concluidos, cancelados; lo más reciente primero."""
    consulta = asignaciones_de(usuario).exclude(evento__estatus__in=ABIERTOS, hasta__gte=timezone.now()).order_by("-desde")
    return list(consulta[:limite])


def tecnicos_con_eventos():
    """[(id, nombre)] de quienes tienen alguna asignación (para filtrar el calendario)."""
    vistos = {}
    for pk, nombre in Asignacion.objects.order_by("tecnico_nombre").values_list("tecnico_id", "tecnico_nombre"):
        vistos.setdefault(pk, nombre)
    return list(vistos.items())


def pagina(items, numero, por_pagina=25):
    return Paginator(items, por_pagina).get_page(numero)
