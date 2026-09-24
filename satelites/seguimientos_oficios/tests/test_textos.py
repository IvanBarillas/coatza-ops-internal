from django.test import SimpleTestCase

from satelites.seguimientos_oficios.textos import coincidencias, normalizar, terminos


class TextosTests(SimpleTestCase):
    def test_normalizar_conserva_la_longitud(self):
        original = "Tesorería ÑANDÚ ß İstanbul café"
        self.assertEqual(len(normalizar(original)), len(original))
        self.assertEqual(normalizar("Tesorería ÑANDÚ"), "tesoreria nandu")

    def test_terminos(self):
        self.assertEqual(terminos("  Instalación   ELÉCTRICA "), ["instalacion", "electrica"])

    def test_pagina_y_fragmento_resaltado_con_texto_original(self):
        texto = "Portada del oficio\fSegunda hoja sin nada\fTercera hoja: se solicita la <b>instalación</b> eléctrica del rack"
        pagina, fragmento = coincidencias(texto, normalizar(texto), "instalacion")[0]
        self.assertEqual(pagina, 3)
        self.assertIn("<mark>instalación</mark>", fragmento)
        self.assertIn("&lt;b&gt;", fragmento)
        self.assertNotIn("<b>", fragmento)

    def test_una_coincidencia_por_pagina_y_ordenadas(self):
        texto = "rack rack rack\fnada\frack de nuevo"
        self.assertEqual([p for p, _ in coincidencias(texto, normalizar(texto), "rack")], [1, 3])

    def test_raiz_cuando_no_hay_coincidencia_literal(self):
        texto = "Se requiere un servidor nuevo"
        self.assertEqual(coincidencias(texto, normalizar(texto), "servidores")[0][0], 1)

    def test_sin_coincidencias(self):
        self.assertEqual(coincidencias("hola", normalizar("hola"), "adios"), [])
