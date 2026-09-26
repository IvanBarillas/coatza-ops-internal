"""El sidebar contextual sigue el contrato del Core: los parciales de #workbench usan el include compartido y nunca su propio aside."""
from pathlib import Path

from django.urls import reverse

from .base import BaseEventos

CARPETA = Path(__file__).resolve().parent.parent / "templates" / "eventos" / "workbench"


class SidebarContextualTests(BaseEventos):
    def test_ningun_parcial_declara_su_propio_aside(self):
        parciales = sorted(CARPETA.glob("*.html"))
        self.assertEqual(len(parciales), 5)
        for parcial in parciales:
            contenido = parcial.read_text()
            self.assertNotIn('id="module-sidebar"', contenido, parcial.name)
            self.assertIn('{% include "shell/_module_sidebar.html" with sidebar_template="eventos/contextual/sidebar.html" %}', contenido, parcial.name)

    def test_el_swap_del_workbench_trae_el_boton_de_contraer(self):
        self.client.force_login(self.diego)
        parcial = self.client.get(reverse("eventos:mis_eventos"), HTTP_HX_REQUEST="true", HTTP_HX_TARGET="workbench")
        self.assertContains(parcial, 'id="module-sidebar-shell"')
        self.assertContains(parcial, "data-axentra-sidebar-toggle")
        self.assertContains(parcial, "ax-sb-hide")
