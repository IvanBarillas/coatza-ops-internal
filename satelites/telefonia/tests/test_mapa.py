from django.test import SimpleTestCase

from satelites.telefonia.mapa import coordenadas_de_texto


class CoordenadasTests(SimpleTestCase):
    def test_formatos_de_google_maps(self):
        casos = {
            "https://www.google.com/maps/place/Duport/@18.1512345,-94.4256789,17z/data=!3m1": (18.1512345, -94.4256789),
            "https://www.google.com/maps?q=18.15,-94.42": (18.15, -94.42),
            "https://www.google.com/maps/place/x/data=!4m2!3d18.2!4d-94.5": (18.2, -94.5),
            "18.1512, -94.4256": (18.1512, -94.4256),
        }
        for texto, esperado in casos.items():
            self.assertEqual(coordenadas_de_texto(texto), esperado, texto)

    def test_rechaza_lo_que_no_son_coordenadas(self):
        for texto in ("https://maps.app.goo.gl/abc123", "", "hola", "95.1, -94.2", "18.1, -200.5"):
            self.assertIsNone(coordenadas_de_texto(texto), texto)
