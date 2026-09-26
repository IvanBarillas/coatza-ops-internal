from django.core.exceptions import ValidationError
from django.test import TestCase

from satelites.telefonia.importacion import importar, leer_csv, leer_kml
from satelites.telefonia.models import Linea

KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>DUPORT OSTION 8</name>
<description><![CDATA[Municipio: Coatzacoalcos<br>Nombre: Unidad Deportiva Duport Ostión 8<br>direccion: Coatzacoalcos Coatzacoalcos Unidad Deportiva<br>telefono: 9212110336<br>paquete: solo internet (300mb simetrico)<br>velocidad:]]></description>
<Point><coordinates>-94.4256,18.1512,0</coordinates></Point></Placemark>
<Placemark><name>SITE TESORERIA</name><description>telefono: C1G-2204-0353</description></Placemark>
</Document></kml>"""


class ImportacionTests(TestCase):
    def test_kml_de_google_mis_mapas(self):
        filas = leer_kml(KML)
        self.assertEqual(len(filas), 2)
        self.assertEqual((filas[0]["identificador"], filas[0]["sitio"], filas[0]["latitud"], filas[0]["longitud"]), ("9212110336", "Unidad Deportiva Duport Ostión 8", "18.1512", "-94.4256"))
        resumen = importar(filas, aplicar=True)
        self.assertEqual((resumen["creadas"], resumen["errores"]), (2, []))
        duport = Linea.objects.get(identificador="9212110336")
        self.assertEqual((duport.tipo, duport.velocidad, float(duport.latitud)), ("internet", "300mb simetrico", 18.1512))
        enlace = Linea.objects.get(identificador="C1G-2204-0353")
        self.assertEqual((enlace.tipo, enlace.sitio, enlace.con_ubicacion), ("enlace", "SITE TESORERIA", False))

    def test_simulacion_no_escribe_y_repetir_no_duplica(self):
        filas = leer_kml(KML)
        self.assertEqual(importar(filas)["creadas"], 2)
        self.assertEqual(Linea.objects.count(), 0)
        importar(filas, aplicar=True)
        segunda = importar(filas, aplicar=True)
        self.assertEqual((segunda["creadas"], segunda["actualizadas"], segunda["sin_cambios"]), (0, 0, 2))
        self.assertEqual(Linea.objects.count(), 2)

    def test_csv_con_columnas_flexibles_y_errores_por_fila(self):
        csv_texto = "Teléfono;Sitio;Latitud;Longitud;Enlace\n9212132439;Módulo predial;18.1;-94.4;\n;Sin número;;;\n9212132439;Repetida;;;\n9212000000;Con enlace;;;https://www.google.com/maps?q=18.2,-94.5\n"
        resumen = importar(leer_csv(csv_texto), aplicar=True)
        self.assertEqual((resumen["creadas"], len(resumen["errores"])), (2, 2))
        self.assertEqual(float(Linea.objects.get(identificador="9212000000").latitud), 18.2)

    def test_actualiza_sin_borrar_lo_que_no_viene(self):
        Linea.objects.create(identificador="9212110336", sitio="Viejo", direccion="Calle 1", latitud=18.0, longitud=-94.0)
        importar([{"identificador": "9212110336", "sitio": "Nuevo nombre"}], aplicar=True)
        linea = Linea.objects.get()
        self.assertEqual((linea.sitio, linea.direccion, float(linea.latitud)), ("Nuevo nombre", "Calle 1", 18.0))

    def test_kml_invalido(self):
        with self.assertRaises(ValidationError):
            leer_kml("esto no es xml")
