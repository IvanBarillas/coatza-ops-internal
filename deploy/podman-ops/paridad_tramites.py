#!/usr/bin/env python3
"""
Paridad de la API de Trámites: `hermes-tramites-app` (la app ORIGINAL) frente al satélite
(`axentra-core` con `axentra-mod-tramites`). Mismas consultas contra las dos; compara estado HTTP,
forma y resultados, y separa las diferencias ESPERADAS de las que no.

Solo librería estándar. Las claves llegan por variables de entorno y nunca se imprimen ni se guardan:

    ORIGINAL_API_KEY   clave X-API-Key de hermes-tramites-app
    SATELITE_API_KEY   clave X-API-Key del Core (INTERNAL_API_KEY)
    ORIGINAL_URL       por defecto http://hermes-tramites-app:8000
    SATELITE_URL       por defecto http://axentra-core:8000

Se ejecuta en una red que alcance a los dos (frontend); ver RUNBOOK. Solo hace GET de lectura.

Diferencias ESPERADAS (no cuentan como fallo):
  acentos   el satélite normaliza acentos al buscar; el original prefiltra con `icontains` en SQL, que distingue
            acentos: hay consultas donde el satélite devuelve MÁS trámites (nunca menos). Se acepta solo si, con
            `limite=50`, lo del original está contenido en lo del satélite y los comunes salen en el mismo orden y
            con el mismo contenido. Que el satélite añada trámites empuja fuera del `limite` a otros: por eso se
            compara ampliando el límite.
  orden-requisitos
            `requisitos` no tiene orden definido en el modelo (sin `Meta.ordering`): el mismo conjunto puede salir
            en otro orden según la base y su historia de escrituras. Se acepta si el CONJUNTO es idéntico.
  costo     el seeder del satélite ya no infiere `costo` del primer número de `costo_texto` (201.0, 136.0,
            198.0, 29.0 eran números de artículo o fecha); en costo variable queda 0 y el texto no cambia.
  ids       los id son de cada base; los trámites se emparejan por título (solo se informa cuántos difieren).
Cualquier otra diferencia sí es un fallo (código de salida 1).
"""
import argparse
import json
import os
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ORIGINAL_URL = os.environ.get("ORIGINAL_URL", "http://hermes-tramites-app:8000").rstrip("/")
SATELITE_URL = os.environ.get("SATELITE_URL", "http://axentra-core:8000").rstrip("/")
RUTA = "/api/v1/tramites/buscar"


class SinRedireccion(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # una redirección (p. ej. a HTTPS) se informa, no se sigue
        return None


ABRIDOR = urllib.request.build_opener(SinRedireccion)


def pedir(base, params, clave):
    url = base + RUTA + ("?" + urllib.parse.urlencode(params) if params else "")
    peticion = urllib.request.Request(url, headers={"X-API-Key": clave} if clave is not None else {})
    inicio = time.perf_counter()
    try:
        with ABRIDOR.open(peticion, timeout=30) as r:
            estado, cuerpo = r.status, r.read()
    except urllib.error.HTTPError as exc:
        estado, cuerpo = exc.code, exc.read()
    except Exception as exc:  # red caída, DNS, tiempo agotado
        return {"estado": None, "error": f"{type(exc).__name__}: {exc}", "ms": 0.0, "json": None}
    ms = (time.perf_counter() - inicio) * 1000
    try:
        datos = json.loads(cuerpo.decode("utf-8")) if cuerpo else None
    except ValueError:
        datos = None
    return {"estado": estado, "ms": ms, "json": datos}


def sin_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).lower()


def sin_ids(x):
    """Los `id` son de cada base de datos: se comparan por título, no por id."""
    if isinstance(x, dict):
        return {k: sin_ids(v) for k, v in x.items() if k != "id"}
    if isinstance(x, list):
        return [sin_ids(v) for v in x]
    return x


def diferencias_de_item(o, s):
    """Campos que difieren entre el mismo trámite en el original (o) y en el satélite (s)."""
    o, s = sin_ids(o), sin_ids(s)
    return sorted(k for k in set(o) | set(s) if o.get(k) != s.get(k))


def costo_esperado(o, s):
    """El único cambio de `costo` esperado: en costo variable el original traía un número de artículo/fecha."""
    return bool(o.get("costo_variable")) and (o.get("costo") or 0) > 0 and (s.get("costo") or 0) == 0


CONSULTAS = [
    # (nombre, parámetros)
    ("trámite exacto", {"termino": "licencia de funcionamiento"}),
    ("trámite exacto 2", {"termino": "traslado de dominio"}),
    ("acta de nacimiento", {"termino": "acta de nacimiento"}),
    ("constancia de residencia", {"termino": "constancia de residencia"}),
    ("predial", {"termino": "predial"}),
    ("matrimonio", {"termino": "matrimonio"}),
    ("alineamiento", {"termino": "alineamiento"}),
    ("perpetuidad", {"termino": "perpetuidad"}),
    ("pregunta larga", {"termino": "cuanto cuesta sacar la licencia de funcionamiento de un negocio"}),
    ("palabras sueltas", {"termino": "licencia negocio comercial"}),
    ("con acento: construcción", {"termino": "construcción"}),
    ("sin acento: construccion", {"termino": "construccion"}),
    ("con acento: cédula", {"termino": "cédula"}),
    ("sin acento: cedula", {"termino": "cedula"}),
    ("con acento: panteón", {"termino": "panteón"}),
    ("sin acento: panteon", {"termino": "panteon"}),
    ("mayúsculas", {"termino": "LICENCIA DE FUNCIONAMIENTO"}),
    ("sin resultados", {"termino": "zzzzqqxx"}),
    ("solo stopwords", {"termino": "de la el"}),
    ("sin término (listado)", {}),
    ("sin término, límite 50", {"limite": 50}),
    ("límite 1", {"termino": "licencia", "limite": 1}),
    ("límite 3", {"termino": "acta", "limite": 3}),
    ("tipo T", {"tipo": "T", "limite": 50}),
    ("tipo S", {"tipo": "S", "limite": 50}),
    ("tipo T con término", {"termino": "licencia", "tipo": "T"}),
    ("límite fuera de rango (0)", {"termino": "acta", "limite": 0}),
    ("límite fuera de rango (51)", {"termino": "acta", "limite": 51}),
    ("parámetro desconocido", {"q": "acta"}),
]


COSTOS_QUE_CAMBIAN = {}  # título -> (costo del original, costo del satélite)


def campos_distintos_esperados(io, is_):
    """-> (fallo|None, esperadas): compara un mismo trámite en las dos bases."""
    campos = diferencias_de_item(io, is_)
    esperadas = set()
    if "requisitos" in campos:
        clave = lambda r: (r.get("perfil"), r.get("descripcion"), r.get("obligatorio"), r.get("fundamento_especifico"))
        if sorted(map(clave, io["requisitos"])) == sorted(map(clave, is_["requisitos"])):
            esperadas.add("orden-requisitos")
            campos.remove("requisitos")
    if "costo" in campos and costo_esperado(io, is_):
        esperadas.add("costo")
        COSTOS_QUE_CAMBIAN[io["titulo"]] = (io["costo"], is_["costo"])
        campos.remove("costo")
    if campos:
        return f"«{io['titulo']}» difiere en {campos}", esperadas
    return None, esperadas


def clasificar(o, s, ampliar):
    """-> (categoría, detalle). Categorías: igual, esperada:<tipos>, fallo.

    `ampliar()` repite la misma consulta con limite=50 en las dos bases (solo si las listas difieren).
    """
    if o["estado"] != s["estado"]:
        return "fallo", f"estado HTTP distinto: original {o['estado']} / satélite {s['estado']}"
    if o["estado"] != 200:
        return ("igual", "") if o["json"] == s["json"] else ("fallo", f"cuerpo de error distinto: {o['json']} / {s['json']}")
    lo, ls = o["json"], s["json"]
    if not isinstance(lo, list) or not isinstance(ls, list):
        return "fallo", "el cuerpo no es una lista en alguno de los dos"
    esperadas, notas = set(), []
    if [i["titulo"] for i in lo] != [i["titulo"] for i in ls]:
        o50, s50 = ampliar()
        if o50["estado"] != 200 or s50["estado"] != 200:
            return "fallo", f"al ampliar el límite: estados {o50['estado']} / {s50['estado']}"
        lo, ls = o50["json"], s50["json"]
        to, ts = [i["titulo"] for i in lo], [i["titulo"] for i in ls]
        if len(set(to)) != len(to) or len(set(ts)) != len(ts):
            return "fallo", "títulos repetidos en el resultado de alguno de los dos"
        if set(to) == set(ts):
            return "fallo", "mismos trámites en distinto orden (límite 50)"
        if not set(to) <= set(ts):
            return "fallo", f"faltan en el satélite {sorted(set(to) - set(ts))[:4]}; sobran {sorted(set(ts) - set(to))[:4]}"
        if to != [t for t in ts if t in set(to)]:
            return "fallo", "los trámites comunes salen en distinto orden"
        extra = [t for t in ts if t not in set(to)]
        esperadas.add("acentos")
        notas.append(f"el satélite añade {len(extra)} (p. ej. «{extra[0]}»)")
        por_titulo = {i["titulo"]: i for i in ls}
        pares = [(i, por_titulo[i["titulo"]]) for i in lo]
    else:
        if len({i["titulo"] for i in lo}) != len(lo):
            return "fallo", "títulos repetidos en el resultado"
        pares = list(zip(lo, ls))
    for io, is_ in pares:
        fallo, extra_esperadas = campos_distintos_esperados(io, is_)
        if fallo:
            return "fallo", fallo
        esperadas |= extra_esperadas
    if not esperadas:
        return "igual", ""
    return "esperada:" + "+".join(sorted(esperadas)), "; ".join(notas)[:300]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", help="guardar el detalle (sin claves) en este archivo")
    args = ap.parse_args()

    clave_o, clave_s = os.environ.get("ORIGINAL_API_KEY"), os.environ.get("SATELITE_API_KEY")
    if not clave_o or not clave_s:
        sys.exit("Faltan ORIGINAL_API_KEY y/o SATELITE_API_KEY en el entorno (nunca como argumento ni en el script).")

    print(f"Original : {ORIGINAL_URL}\nSatélite : {SATELITE_URL}\n")
    # Comprobación previa: sin conexión o con el Host rechazado, todo lo demás sería ruido.
    for nombre, base, clave in (("original", ORIGINAL_URL, clave_o), ("satélite", SATELITE_URL, clave_s)):
        r = pedir(base, {"termino": "acta", "limite": 1}, clave)
        if r["estado"] is None:
            sys.exit(f"No se pudo conectar con el {nombre} ({base}): {r['error']}")
        if r["estado"] == 400:
            sys.exit(f"El {nombre} respondió 400: su ALLOWED_HOSTS no incluye el host de {base}.")
        if r["estado"] in (301, 302):
            sys.exit(f"El {nombre} redirige (¿a HTTPS?): revise SECURE_REDIRECT_EXEMPT=^api/v1/ (satélite) o use su URL interna.")
        if r["estado"] == 401:
            sys.exit(f"El {nombre} rechazó la clave (401): revise {'ORIGINAL' if nombre == 'original' else 'SATELITE'}_API_KEY.")
    filas, ms_o, ms_s = [], [], []

    def comparar(nombre, params, claves=(clave_o, clave_s)):
        o, s = pedir(ORIGINAL_URL, params, claves[0]), pedir(SATELITE_URL, params, claves[1])
        if o["estado"] is None or s["estado"] is None:
            categoria, detalle = "fallo", f"sin respuesta: original={o.get('error')} satélite={s.get('error')}"
        else:
            ampliar = lambda: (pedir(ORIGINAL_URL, {**params, "limite": 50}, claves[0]),
                               pedir(SATELITE_URL, {**params, "limite": 50}, claves[1]))
            categoria, detalle = clasificar(o, s, ampliar)
            ms_o.append(o["ms"]), ms_s.append(s["ms"])
        n = lambda r: len(r["json"]) if isinstance(r.get("json"), list) else "-"
        filas.append({"consulta": nombre, "params": params, "categoria": categoria, "detalle": detalle,
                      "estado": [o["estado"], s["estado"]], "resultados": [n(o), n(s)]})
        return o, s

    # Autenticación: sin clave y con clave incorrecta deben rechazar igual en los dos.
    for nombre, clave in (("sin X-API-Key", None), ("X-API-Key incorrecta", "clave-incorrecta")):
        comparar(f"auth: {nombre}", {"termino": "acta"}, claves=(clave, clave))

    vistos = {}
    for nombre, params in CONSULTAS:
        o, s = comparar(nombre, params)
        for lado, r in (("original", o), ("satelite", s)):
            if r["estado"] == 200 and isinstance(r["json"], list):
                for item in r["json"]:
                    vistos.setdefault(item["titulo"], {})[lado] = item["id"]

    # Barrido por título: cada trámite visto en cualquiera de los dos debe encontrarse en ambos por su
    # propio título (así se detecta un trámite que falta en una base sin depender de los ids).
    solo_o, solo_s, ids_comunes, ids_distintos = [], [], 0, 0
    for titulo in sorted(vistos):
        o, s = comparar(f"título: {titulo[:48]}", {"termino": titulo, "limite": 5})
        en_o = o["estado"] == 200 and titulo in [i["titulo"] for i in o["json"]]
        en_s = s["estado"] == 200 and titulo in [i["titulo"] for i in s["json"]]
        if en_o and not en_s:
            solo_o.append(titulo)
        elif en_s and not en_o:
            solo_s.append(titulo)
        elif en_o and en_s:
            ids_comunes += 1
            id_o = next(i["id"] for i in o["json"] if i["titulo"] == titulo)
            id_s = next(i["id"] for i in s["json"] if i["titulo"] == titulo)
            ids_distintos += id_o != id_s

    conteo = {}
    for f in filas:
        conteo[f["categoria"]] = conteo.get(f["categoria"], 0) + 1
    fallos = [f for f in filas if f["categoria"] == "fallo"]
    esperadas = [f for f in filas if f["categoria"].startswith("esperada")]

    print(f"{'CONSULTAS':<32}{len(filas)}")
    print(f"{'  idénticas':<32}{conteo.get('igual', 0)}")
    tipos = {}
    for f in esperadas:
        for tipo in f["categoria"].split(":")[1].split("+"):
            tipos[tipo] = tipos.get(tipo, 0) + 1
    print(f"{'  con diferencias esperadas':<32}{len(esperadas)}  (" + ", ".join(f"{t}: {n}" for t, n in sorted(tipos.items())) + ")")
    print(f"{'  FALLOS (inesperadas)':<32}{len(fallos)}")
    print(f"{'Trámites vistos (unión)':<32}{len(vistos)}  | solo en el original: {len(solo_o)} | solo en el satélite: {len(solo_s)}")
    print(f"{'Mismo trámite, id distinto':<32}{ids_distintos} de {ids_comunes}  (informativo: ids propios de cada base)")
    if ms_o:
        print(f"{'Latencia mediana (ms)':<32}original {statistics.median(ms_o):.0f} | satélite {statistics.median(ms_s):.0f}")
    for f in esperadas:
        if "acentos" in f["categoria"]:
            print(f"\nEjemplo (acentos): {f['consulta']}: {f['detalle']}")
            break
    if COSTOS_QUE_CAMBIAN:
        print(f"\nCostos que cambian por el seeder ({len(COSTOS_QUE_CAMBIAN)} trámites; original -> satélite):")
        for titulo, (co, cs) in sorted(COSTOS_QUE_CAMBIAN.items()):
            print(f"  {co:>8} -> {cs:<4} {titulo[:70]}")
    if fallos or solo_o or solo_s:
        print("\nDIFERENCIAS INESPERADAS:")
        for f in fallos[:40]:
            print(f"  {f['consulta']}: {f['detalle']}")
        for t in solo_o[:20]:
            print(f"  solo en el original: {t}")
        for t in solo_s[:20]:
            print(f"  solo en el satélite: {t}")
    print("\nRESULTADO:", "PARIDAD OK (solo diferencias esperadas)" if not (fallos or solo_o or solo_s) else "HAY DIFERENCIAS INESPERADAS")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"filas": filas, "solo_original": solo_o, "solo_satelite": solo_s}, f, ensure_ascii=False, indent=1)
    sys.exit(1 if (fallos or solo_o or solo_s) else 0)


if __name__ == "__main__":
    main()
