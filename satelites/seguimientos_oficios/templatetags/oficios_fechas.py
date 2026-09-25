from datetime import date

from django import template

register = template.Library()


@register.filter
def fecha_iso(valor):
    """Convierte una fecha guardada como texto AAAA-MM-DD (bitácora) a dd/mm/aaaa; si no se puede, la deja igual."""
    try:
        return date.fromisoformat(str(valor)).strftime("%d/%m/%Y")
    except ValueError:
        return valor
