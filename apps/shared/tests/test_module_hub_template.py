from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ModuleHubTemplateTests(SimpleTestCase):
    def test_hub_uses_the_scalable_launcher_partial(self):
        templates_dir = Path(settings.BASE_DIR) / "templates"
        hub_template = (templates_dir / "index_hub.html").read_text(
            encoding="utf-8"
        )
        launcher_template = (
            templates_dir / "launcher" / "_content.html"
        ).read_text(encoding="utf-8")

        page_content_template = (
            templates_dir / "launcher" / "_page_content.html"
        ).read_text(encoding="utf-8")

        self.assertIn(
            '{% include "launcher/_page_content.html" %}',
            hub_template,
        )
        self.assertIn(
            '{% include "launcher/_content.html" %}',
            page_content_template,
        )
        self.assertIn('id="launcher-content"', launcher_template)
        self.assertIn("application_page", launcher_template)
        self.assertIn("core_cards", launcher_template)
        self.assertIn('hx-get=', launcher_template)
        self.assertIn('hx-swap="outerHTML"', launcher_template)
        self.assertIn("has_previous", launcher_template)
        self.assertIn("has_next", launcher_template)

    def test_launcher_is_not_an_installer(self):
        launcher_template = (
            Path(settings.BASE_DIR)
            / "templates"
            / "launcher"
            / "_content.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn("Cómo instalar este módulo", launcher_template)
        self.assertNotIn("Distribución:", launcher_template)
        self.assertIn("Activar", launcher_template)
        self.assertIn("Desactivar", launcher_template)

        def test_authenticated_navigation_links_to_applications(self):
            navbar_template = (
                Path(settings.BASE_DIR)
                / "templates"
                / "partials"
                / "navbar.html"
            ).read_text(encoding="utf-8")

            self.assertIn("{% url 'index_hub' %}", navbar_template)
            self.assertIn("Aplicaciones", navbar_template)
            self.assertIn('data-lucide="grid-2x2"', navbar_template)
            self.assertNotIn("Ir a la Estación Central", navbar_template)