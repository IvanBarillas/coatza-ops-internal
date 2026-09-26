"""El sidebar contextual sigue el contrato del Core: los parciales de #workbench usan el include compartido (con el botón
de contraer) y nunca un <aside id="module-sidebar"> propio."""
from pathlib import Path

from django.urls import reverse

from .base import BaseAdjuntos

CARPETA = Path(__file__).resolve().parent.parent / "templates" / "seguimientos_oficios" / "workbench"


class SidebarContextualTests(BaseAdjuntos):
    def test_ningun_parcial_declara_su_propio_aside(self):
        parciales = sorted(CARPETA.glob("*.html"))
        self.assertGreater(len(parciales), 10)
        for parcial in parciales:
            contenido = parcial.read_text()
            self.assertNotIn('id="module-sidebar"', contenido, parcial.name)
            if parcial.name != "inicio.html":  # el panel de inicio se muestra sin menú lateral
                self.assertIn('{% include "shell/_module_sidebar.html" with sidebar_template="seguimientos_oficios/contextual/oficios_sidebar.html" %}', contenido, parcial.name)

    def test_el_swap_del_workbench_trae_el_boton_de_contraer(self):
        self.client.force_login(self.user)
        parcial = self.client.get(reverse("seguimientos_oficios:documento_list"), HTTP_HX_REQUEST="true", HTTP_HX_TARGET="workbench")
        self.assertContains(parcial, 'id="module-sidebar-shell"')
        self.assertContains(parcial, "data-axentra-sidebar-toggle")
        self.assertContains(parcial, "ax-sb-hide")  # encabezado estándar: los textos se pliegan al contraer
        completa = self.client.get(reverse("seguimientos_oficios:documento_list"))
        self.assertContains(completa, "data-axentra-sidebar-toggle")
