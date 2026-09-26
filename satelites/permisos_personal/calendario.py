"""Reglas de fechas: periodos (semestres), días hábiles y antigüedad. Sin acceso a la base de datos."""
import datetime

PERIODOS = {
    1: ((1, 1), (6, 30)),
    2: ((7, 1), (12, 31)),
}
NOMBRES_PERIODO = {1: "1.er periodo (enero a junio)", 2: "2.º periodo (julio a diciembre)"}


def limites_periodo(anio, periodo):
    (mi, di), (mf, df) = PERIODOS[periodo]
    return datetime.date(anio, mi, di), datetime.date(anio, mf, df)


def periodo_de(fecha):
    """(año, periodo) al que pertenece una fecha."""
    return fecha.year, 1 if fecha.month <= 6 else 2


def es_habil(fecha):
    return fecha.weekday() < 5  # lunes a viernes


def rango(inicio, fin):
    return [inicio + datetime.timedelta(days=n) for n in range((fin - inicio).days + 1)]


def dias_habiles(inicio, fin):
    """Fechas de lunes a viernes entre inicio y fin, ambos incluidos."""
    return [d for d in rango(inicio, fin) if es_habil(d)]


def anios_de_antiguedad(fecha_ingreso, fecha_referencia):
    """Años cumplidos de servicio a la fecha de referencia."""
    if fecha_ingreso is None or fecha_referencia < fecha_ingreso:
        return 0
    anios = fecha_referencia.year - fecha_ingreso.year
    if (fecha_referencia.month, fecha_referencia.day) < (fecha_ingreso.month, fecha_ingreso.day):
        anios -= 1
    return anios
