"""Áreas del menú lateral: cada una tiene su propia lista de opciones y el selector de arriba cambia entre ellas."""
from django.urls import reverse

AREAS = (
    ("oficios", "Oficios", "file-text"),
    ("prestamos", "Préstamos", "hand-coins"),
    ("soporte", "Soporte técnico", "stethoscope"),
)
RUTAS_DE_PRESTAMOS = {
    "prestamos", "vales", "vale_crear", "vale_imprimir", "vale_devolucion",
    "vale_editar", "bienes", "bien_crear", "bien_detalle", "bien_editar",
}
RUTAS_DE_SOPORTE = {
    "soporte", "soporte_crear_diagnostico", "soporte_crear_baja", "soporte_crear_alta", "soporte_imprimir", "soporte_editar",
}


def _nombre_de_ruta(nombre_completo):
    return (nombre_completo or "").rpartition(":")[2]


def area_de(nombre_ruta):
    ruta = _nombre_de_ruta(nombre_ruta)
    return "prestamos" if ruta in RUTAS_DE_PRESTAMOS else "soporte" if ruta in RUTAS_DE_SOPORTE else "oficios"


def construir_menu(request, area_forzada=None):
    """Devuelve (opciones del área actual, selector de áreas, área actual) según los permisos del usuario."""
    actual = request.resolver_match.view_name if request.resolver_match else ""
    por_area = {clave: [] for clave, _, _ in AREAS}
    for item in getattr(request, "axentra_sidebar_menu", []):
        area = area_de(item["url"])
        por_area[area].append({
            "icon": item["icon"], "name": item["name"], "href": reverse(item["url"]),
            "active": item["url"] == actual,
        })
    disponibles = [(c, n, i) for c, n, i in AREAS if por_area[c]]
    claves = [c for c, _, _ in disponibles]
    area_actual = area_forzada or area_de(actual)
    if area_actual not in claves and claves:
        area_actual = claves[0]
    selector = []
    if len(disponibles) > 1:
        selector = [
            {"clave": c, "nombre": n, "icon": i, "href": por_area[c][0]["href"], "activa": c == area_actual}
            for c, n, i in disponibles
        ]
    datos = next(((c, n, i) for c, n, i in AREAS if c == area_actual), AREAS[0])
    return por_area[area_actual], selector, {"clave": datos[0], "nombre": datos[1], "icon": datos[2]}
