"""Capacidades que este satélite ofrece a otros, por nombre (contrato en docs/contratos-satelites.md).

`vinculos.eventos`: dado un objeto de otro satélite (tipo + UUID), qué eventos lo usan. Quien consulta no importa este satélite; si no está
instalado, la consulta devuelve vacío. Solo responde a quien puede ver los eventos (`can_view_all_events`).
"""
from django.core.exceptions import ValidationError
from django.urls import reverse

from .models import Evento
from .integracion import tiene_permiso
from .selectors import APP_SLUG


def _ficha(evento, relacion):
    return {
        "tipo": "eventos.evento", "id": str(evento.pk), "etiqueta": f"{evento.nombre} · {evento.inicio:%d/%m/%Y}", "detalle": evento.lugar,
        "estado": evento.get_estatus_display(), "url": reverse("eventos:evento_detalle", args=[evento.pk]), "relacion": relacion,
    }


class ProveedorVinculos:
    NOMBRE = "vinculos.eventos"
    available = True

    # tipo del objeto que se consulta -> (filtro sobre Evento, texto de la relación)
    RELACIONES = {
        "prestamos.vale": ("vales__ref_id", "Salió al evento"),
        "telefonia.linea": ("tramites__ref_id", "Trámite en el evento"),
    }

    def vinculos_de(self, request, tipo, ref_id):
        """Fichas de los eventos relacionados con el objeto (`tipo` + UUID); lista vacía si no aplica o no hay permiso."""
        relacion = self.RELACIONES.get(tipo)
        if not relacion or not (request.axentra_is_root or tiene_permiso(request.user, APP_SLUG, "can_view_all_events")):
            return []
        try:
            eventos = list(Evento.objects.filter(**{relacion[0]: ref_id}).distinct().order_by("-inicio")[:20])
        except (ValueError, TypeError, ValidationError):
            return []
        return [_ficha(e, relacion[1]) for e in eventos]
