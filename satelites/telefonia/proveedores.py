"""Capacidades que este satélite ofrece a otros, por nombre (contrato en docs/contratos-satelites.md).

Los consumidores piden `telefonia.lineas` al registro de integraciones; sin este satélite reciben una integración nula.
Las consultas respetan el permiso del usuario de la petición (`can_view_reports`).
"""
from django.core.exceptions import ValidationError
from django.urls import reverse

from . import selectors as sel
from .integracion import tiene_permiso


def _ficha(linea):
    return {
        "tipo": ProveedorLineas.TIPO,
        "id": str(linea.pk),
        "etiqueta": f"{linea.identificador} · {linea.sitio}",
        "detalle": " ".join(x for x in (linea.get_tipo_display(), linea.velocidad) if x),
        "estado": "activa" if linea.is_active else "inactiva",
        "url": reverse("telefonia:linea_detalle", args=[linea.pk]),
    }


class ProveedorLineas:
    """Líneas telefónicas, internet y enlaces dedicados."""

    NOMBRE = "telefonia.lineas"
    TIPO = "telefonia.linea"
    available = True

    def _visibles(self, request):
        if not (request.axentra_is_root or tiene_permiso(request.user, sel.APP_SLUG, "can_view_reports")):
            return sel.Linea.objects.none()
        return sel.lineas_visibles(request)

    def resolver(self, request, ref_id):
        """Ficha de la línea o None si no existe o el usuario no puede verla."""
        try:
            linea = self._visibles(request).filter(pk=ref_id).first()
        except (ValueError, TypeError, ValidationError):
            return None
        return _ficha(linea) if linea else None

    def buscar(self, request, texto="", *, limite=20, solo_activas=True):
        consulta = sel.buscar_lineas(self._visibles(request), texto)
        if solo_activas:
            consulta = consulta.filter(is_active=True)
        return [_ficha(l) for l in consulta.order_by("sitio", "identificador")[:limite]]
