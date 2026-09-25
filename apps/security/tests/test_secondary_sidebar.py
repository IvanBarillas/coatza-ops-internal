from django.contrib.staticfiles import finders
from django.template.loader import get_template
from django.test import SimpleTestCase


class SecondarySidebarAssetsTests(SimpleTestCase):
    def test_shell_base_compiles(self):
        self.assertIsNotNone(get_template("shell/base.html"))

    def test_secondary_sidebar_controller_is_discoverable(self):
        asset_path = finders.find("js/axentra-secondary-sidebar.js")
        self.assertTrue(asset_path)

        with open(asset_path, encoding="utf-8") as asset:
            source = asset.read()

        self.assertIn("htmx:pushedIntoHistory", source)
        self.assertIn("aria-current", source)
        self.assertIn("AxentraSecondarySidebar", source)


class CollapsibleModuleSidebarTests(SimpleTestCase):
    def test_collapse_controller_is_discoverable_and_persists_state(self):
        asset_path = finders.find("js/axentra-sidebar-collapse.js")
        self.assertTrue(asset_path)

        with open(asset_path, encoding="utf-8") as asset:
            source = asset.read()

        self.assertIn("axentra.moduleSidebar", source)
        self.assertIn("htmx:afterSwap", source)
        self.assertIn("aria-expanded", source)

    def test_workbench_renders_toggle_and_shell_loads_controller(self):
        workbench = get_template("shell/workbench.html").template.source
        base = get_template("shell/base.html").template.source

        self.assertIn("data-axentra-sidebar-toggle", workbench)
        self.assertIn('id="module-sidebar"', workbench)
        self.assertIn("axentra-sidebar-collapse.js", base)
        # El estado inicial se aplica en <head> para evitar el parpadeo expandido.
        self.assertIn('localStorage.getItem("axentra.moduleSidebar")', base)

    def test_contextual_sidebars_mark_text_to_hide_when_collapsed(self):
        for name in (
            "security/contextual/security_sidebar.html",
            "accounts/contextual/funcionario_sidebar.html",
            "organigrama/contextual/sede_sidebar.html",
            "organigrama/contextual/dependencia_sidebar.html",
            "organigrama/contextual/area_sidebar.html",
            "security/contextual/configuration_sidebar.html",
        ):
            with self.subTest(template=name):
                self.assertIn("ax-sb-hide", get_template(name).template.source)
