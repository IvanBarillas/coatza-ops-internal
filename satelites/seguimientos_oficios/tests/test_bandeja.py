import os
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from satelites.seguimientos_oficios import bandeja

PDF = b"%PDF-1.4\n%prueba\n"


class ImportacionDeCarpetaTests(SimpleTestCase):
    """Utilidades de carpeta que usa el importador del histórico (línea de comandos)."""

    def setUp(self):
        self._raiz = tempfile.TemporaryDirectory()
        self.addCleanup(self._raiz.cleanup)
        self.raiz = Path(self._raiz.name).resolve()
        override = override_settings(OFICIOS_BANDEJA_RAIZ=str(self.raiz))
        override.enable()
        self.addCleanup(override.disable)
        (self.raiz / "historico").mkdir()

    def test_resolver_rechaza_salidas_de_la_raiz(self):
        for mala in ("../fuera", "historico/../../fuera", "no/existe"):
            with self.assertRaises(bandeja.BandejaError):
                bandeja.resolver(mala)
        fuera = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, fuera)
        os.symlink(fuera, self.raiz / "enlace")
        with self.assertRaises(bandeja.BandejaError):
            bandeja.resolver("enlace")

    def test_resolver_acepta_una_carpeta_valida(self):
        self.assertEqual(bandeja.resolver("/historico/"), self.raiz / "historico")

    def test_listado_solo_pdfs_sin_recursion_ocultos_ni_enlaces(self):
        carpeta = self.raiz / "historico"
        (carpeta / "bueno.PDF").write_bytes(PDF)
        (carpeta / "nota.txt").write_bytes(b"x")
        (carpeta / ".oculto.pdf").write_bytes(PDF)
        (carpeta / "sub").mkdir()
        (carpeta / "sub" / "profundo.pdf").write_bytes(PDF)
        os.symlink(carpeta / "bueno.PDF", carpeta / "enlace.pdf")
        self.assertEqual([a["nombre"] for a in bandeja.listar_pdfs(carpeta)], ["bueno.PDF"])

    def test_leer_rechaza_nombres_con_ruta_y_archivos_inexistentes(self):
        carpeta = self.raiz / "historico"
        (carpeta / "a.pdf").write_bytes(PDF)
        (self.raiz / "secreto.pdf").write_bytes(PDF)
        self.assertEqual(bandeja.leer(carpeta, "a.pdf", tamano_maximo=1000), PDF)
        for nombre in ("../secreto.pdf", "/etc/passwd", "no-existe.pdf", "a.txt", ""):
            with self.assertRaises(bandeja.BandejaError):
                bandeja.leer(carpeta, nombre, tamano_maximo=1000)
        with self.assertRaises(bandeja.BandejaError):
            bandeja.leer(carpeta, "a.pdf", tamano_maximo=3)
