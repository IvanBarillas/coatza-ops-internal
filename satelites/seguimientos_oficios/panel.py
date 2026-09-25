"""Cifras del panel de inicio: qué requiere atención en cada área, según lo que el usuario puede ver."""
from .models import Documento
from .selectors import (
    PENDIENTES, color_semaforo, documentos_de_gestor, documentos_seguimiento, documentos_visibles, permitido,
)


def _cifra(etiqueta, valor, tono=""):
    return {"etiqueta": etiqueta, "valor": valor, "tono": tono if valor else ""}


def _oficios(request):
    cifras = []
    if permitido(request, "can_view_own_pendings"):
        cifras.append(_cifra("Mis pendientes", documentos_de_gestor(request).count(), "ambar"))
    if permitido(request, "can_view_tracking"):
        pendientes = list(documentos_seguimiento(request))
        rojos = sum(1 for d in pendientes if color_semaforo(d.dias_pendiente) == "rojo")
        cifras += [_cifra("Pendientes", len(pendientes)), _cifra("En rojo", rojos, "rojo")]
    elif permitido(request, "can_view_oficios"):
        cifras.append(_cifra("Documentos", documentos_visibles(request).count()))
    return cifras


def _prestamos(request):
    from .prestamos import selectors as sel

    situaciones = [p.situacion for p in sel.prestamos_visibles(request)]
    abiertos = sum(1 for s in situaciones if s in ("vigente", "por_vencer", "vencido"))
    return [
        _cifra("Abiertos", abiertos), _cifra("Por vencer", situaciones.count("por_vencer"), "ambar"),
        _cifra("Vencidos", situaciones.count("vencido"), "rojo"),
    ]


def _soporte(request):
    from .soporte import selectors as sel

    dictamenes = sel.dictamenes_visibles(request)
    por_entregar = dictamenes.filter(documento__estado__in=PENDIENTES).count()
    return [_cifra("Emitidos", dictamenes.exclude(documento__estado=Documento.Estado.CANCELADO).count()), _cifra("Por entregar", por_entregar, "ambar")]


CIFRAS = {"oficios": _oficios, "prestamos": _prestamos, "soporte": _soporte}


def tarjetas(request, areas):
    return [{**area, "cifras": CIFRAS[area["clave"]](request)} for area in areas]
