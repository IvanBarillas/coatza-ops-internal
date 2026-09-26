"""Capacidades que este satélite ofrece a otros, por nombre (contrato en docs/contratos-satelites.md).

Los consumidores no importan nada de aquí: piden `prestamos.vales` al registro de integraciones y, si esta app no está
instalada, reciben una integración nula. Todas las consultas respetan los permisos y el alcance del usuario de la petición.
"""
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.urls import reverse

from .prestamos import selectors as sel


def _ficha(prestamo):
    documento = prestamo.documento
    bienes = [r.bien.nombre for r in prestamo.renglones.all()]
    return {
        "tipo": ProveedorVales.TIPO,
        "id": str(documento.pk),
        "etiqueta": f"{documento.folio or 'Sin folio'} · {documento.contraparte}",
        "detalle": ", ".join(bienes),
        "estado": prestamo.situacion,
        "url": reverse("seguimientos_oficios:vale_imprimir", args=[documento.pk]),
    }


class ProveedorVales:
    """Vales de salida (préstamos de bienes)."""

    NOMBRE = "prestamos.vales"
    TIPO = "prestamos.vale"
    available = True

    def _visibles(self, request):
        return sel.prestamos_visibles(request)

    def resolver(self, request, ref_id):
        """Ficha del vale (etiqueta, estado y URL actuales) o None si no existe o el usuario no puede verlo."""
        try:
            prestamo = self._visibles(request).filter(documento_id=ref_id).first()
        except (ValueError, TypeError, ValidationError):
            return None
        return _ficha(prestamo) if prestamo else None

    def buscar(self, request, texto="", *, limite=20, solo_abiertos=True):
        """Vales que el usuario puede ver, para elegirlos en un selector."""
        consulta = self._visibles(request)
        if texto.strip():
            consulta = consulta.filter(
                Q(documento__folio__icontains=texto) | Q(documento__contraparte__icontains=texto) | Q(documento__asunto__icontains=texto)
            )
        fichas = [_ficha(p) for p in consulta.order_by("-fecha_entrega")[: limite * 3]]
        if solo_abiertos:
            fichas = [f for f in fichas if f["estado"] in ("vigente", "por_vencer", "vencido")]
        return fichas[:limite]
