import datetime

from django.test import SimpleTestCase

from satelites.permisos_personal import calendario as cal


class CalendarioTests(SimpleTestCase):
    def test_periodos_son_los_semestres(self):
        self.assertEqual(cal.periodo_de(datetime.date(2026, 6, 30)), (2026, 1))
        self.assertEqual(cal.periodo_de(datetime.date(2026, 7, 1)), (2026, 2))
        self.assertEqual(cal.limites_periodo(2026, 2), (datetime.date(2026, 7, 1), datetime.date(2026, 12, 31)))

    def test_dias_habiles_son_de_lunes_a_viernes(self):
        lunes, domingo = datetime.date(2026, 3, 2), datetime.date(2026, 3, 8)
        self.assertEqual(len(cal.dias_habiles(lunes, domingo)), 5)
        self.assertEqual(cal.dias_habiles(datetime.date(2026, 3, 7), datetime.date(2026, 3, 8)), [])  # sábado y domingo

    def test_antiguedad_en_anios_cumplidos(self):
        ingreso = datetime.date(2019, 6, 15)
        self.assertEqual(cal.anios_de_antiguedad(ingreso, datetime.date(2026, 6, 14)), 6)
        self.assertEqual(cal.anios_de_antiguedad(ingreso, datetime.date(2026, 6, 15)), 7)
        self.assertEqual(cal.anios_de_antiguedad(ingreso, datetime.date(2018, 1, 1)), 0)
