"""El sidebar contextual sigue el contrato del Core: los parciales de #workbench usan el include compartido (con el botón
de contraer) y nunca un <aside id="module-sidebar"> propio."""
from pathlib import Path

from django.test import override_settings
from django.urls import reverse

from .base import BaseTelefonia

CARPETA = Path(__file__).resolve().parent.parent / "templates" / "telefonia" / "workbench"


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class SidebarContextualTests(BaseTelefonia):
    def test_ningun_parcial_declara_su_propio_aside(self):
        parciales = sorted(CARPETA.glob("*.html"))
        self.assertEqual(len(parciales), 9)
        for parcial in parciales:
            contenido = parcial.read_text()
            self.assertNotIn('id="module-sidebar"', contenido, parcial.name)
            self.assertIn('{% include "shell/_module_sidebar.html" with sidebar_template="telefonia/contextual/sidebar.html" %}', contenido, parcial.name)

    def test_el_swap_del_workbench_trae_el_boton_de_contraer(self):
        self.client.force_login(self.operador)
        parcial = self.client.get(reverse("telefonia:reportes"), HTTP_HX_REQUEST="true", HTTP_HX_TARGET="workbench")
        self.assertContains(parcial, 'id="module-sidebar-shell"')
        self.assertContains(parcial, "data-axentra-sidebar-toggle")
        self.assertContains(parcial, "ax-sb-hide")
        self.assertContains(self.client.get(reverse("telefonia:reportes")), "data-axentra-sidebar-toggle")
