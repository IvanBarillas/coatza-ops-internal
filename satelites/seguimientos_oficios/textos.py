import re
import unicodedata

from django.utils.html import escape
from django.utils.safestring import mark_safe

SALTO_PAGINA = "\f"
CONTEXTO = 70


def normalizar(texto):
    """Minúsculas y sin acentos, conservando la longitud (un carácter por carácter) para poder
    localizar en el texto original lo que se encontró en el normalizado."""
    salida = []
    for caracter in texto or "":
        sin_marcas = "".join(c for c in unicodedata.normalize("NFD", caracter) if not unicodedata.combining(c))
        base = (sin_marcas or caracter).lower()
        salida.append(base[0] if base else caracter)
    return "".join(salida)


def terminos(consulta):
    return [t for t in normalizar(consulta).split() if t]


def _posiciones(normalizado, termino):
    """Busca el término; si no aparece literal (p. ej. 'servidores' vs 'servidor'), prueba su raíz."""
    for candidato in (termino, termino[: max(4, len(termino) - 2)] if len(termino) > 5 else ""):
        if not candidato:
            continue
        inicio = normalizado.find(candidato)
        if inicio != -1:
            yield candidato, inicio
            inicio = normalizado.find(candidato, inicio + len(candidato))
            while inicio != -1:
                yield candidato, inicio
                inicio = normalizado.find(candidato, inicio + len(candidato))
            return


def coincidencias(texto, normalizado, consulta, limite=3):
    """[(pagina, fragmento_html)] con las primeras coincidencias, una por página como máximo."""
    encontradas, paginas_vistas = [], set()
    for termino in terminos(consulta):
        for candidato, pos in _posiciones(normalizado, termino):
            pagina = texto.count(SALTO_PAGINA, 0, pos) + 1
            if pagina in paginas_vistas:
                continue
            paginas_vistas.add(pagina)
            encontradas.append((pagina, _fragmento(texto, pos, len(candidato))))
    encontradas.sort(key=lambda par: par[0])
    return encontradas[:limite]


def _fragmento(texto, pos, largo):
    inicio, fin = max(0, pos - CONTEXTO), min(len(texto), pos + largo + CONTEXTO)
    antes = re.sub(r"\s+", " ", texto[inicio:pos].replace(SALTO_PAGINA, " "))
    dentro = re.sub(r"\s+", " ", texto[pos:pos + largo].replace(SALTO_PAGINA, " "))
    despues = re.sub(r"\s+", " ", texto[pos + largo:fin].replace(SALTO_PAGINA, " "))
    return mark_safe(
        f"{'…' if inicio else ''}{escape(antes)}<mark>{escape(dentro)}</mark>{escape(despues)}{'…' if fin < len(texto) else ''}"
    )
