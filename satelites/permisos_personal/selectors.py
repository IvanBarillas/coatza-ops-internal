from django.core.paginator import Paginator

from .models import Empleado, Solicitud

APP_SLUG = "permisos_personal"


def permitido(request, llave):
    return request.axentra_is_root or llave in request.axentra_permissions_list


def empleado_de(request):
    """El empleado activo que corresponde al usuario, o None si no está dado de alta."""
    return Empleado.objects.filter(usuario=request.user, is_active=True).select_related("usuario").first()


def solicitudes_todas():
    return Solicitud.objects.select_related("empleado__usuario", "validado_por")


def pagina(items, numero, por_pagina=25):
    return Paginator(items, por_pagina).get_page(numero)
