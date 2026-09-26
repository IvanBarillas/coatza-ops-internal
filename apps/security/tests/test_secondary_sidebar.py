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
        toggle = get_template("shell/_module_sidebar_toggle.html").template.source
        base = get_template("shell/base.html").template.source

        self.assertIn("data-axentra-sidebar-toggle", toggle)
        self.assertIn("shell/_module_sidebar_toggle.html", workbench)
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

    def test_every_workbench_partial_uses_the_shared_sidebar_with_toggle(self):
        """Los parciales de #workbench (swap HTMX desde el menu global) deben
        pasar por el include compartido; un <aside> propio se quedaria sin boton."""
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        partials = list((root / "apps").glob("**/templates/**/workbench/*_workbench.html"))
        self.assertTrue(partials)

        for path in partials:
            source = path.read_text(encoding="utf-8")
            with self.subTest(template=str(path.relative_to(root))):
                self.assertNotIn('id="module-sidebar"', source)
                if "_sidebar.html" in source:
                    self.assertIn("shell/_module_sidebar.html", source)

        shared = get_template("shell/_module_sidebar.html").template.source
        self.assertIn("shell/_module_sidebar_toggle.html", shared)

    def test_shell_style_comments_are_balanced(self):
        """Un `*/` dentro de un comentario CSS (p. ej. en `h-*/w-*`) lo cierra antes de
        tiempo y el navegador descarta en silencio la regla siguiente: la transicion
        del sidebar no corria por eso."""
        import re

        source = get_template("shell/base.html").template.source
        blocks = re.findall(r"<style>(.*?)</style>", source, re.S)
        self.assertTrue(blocks)

        for block in blocks:
            stripped = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
            self.assertNotIn("*/", stripped)
            self.assertNotIn("/*", stripped)

    def test_contextual_sidebars_share_the_standard_header(self):
        """Todos usan el mismo encabezado; su icono es shrink-0 porque, sin eso, el
        flexbox lo aplastaba al plegarse el texto (Seguridad, Identidad y Area)."""
        header = get_template("shell/_sidebar_header.html").template.source
        self.assertIn("shrink-0", header)
        self.assertIn("ax-sb-hide", header)

        for name in (
            "security/contextual/security_sidebar.html",
            "accounts/contextual/funcionario_sidebar.html",
            "organigrama/contextual/sede_sidebar.html",
            "organigrama/contextual/dependencia_sidebar.html",
            "organigrama/contextual/area_sidebar.html",
            "security/contextual/configuration_sidebar.html",
        ):
            with self.subTest(template=name):
                self.assertIn("shell/_sidebar_header.html", get_template(name).template.source)


class OrganigramaListHeadersTests(SimpleTestCase):
    """El encabezado de las listas va solo (como Usuarios), no dentro de otra tarjeta."""

    def test_list_header_renders_optional_count_chips(self):
        header = get_template("components/list_header.html").template.source

        self.assertIn("count_total is not None", header)
        self.assertIn("count_active is not None", header)
        self.assertIn("count_inactive is not None", header)

    def test_lists_use_header_counts_instead_of_wrapping_stat_cards(self):
        for name in ("sede", "dependencia", "area"):
            source = get_template(f"organigrama/content/{name}_list_content.html").template.source
            with self.subTest(list=name):
                self.assertIn("count_total=", source)
                self.assertNotIn("rounded-[28px]", source)
                self.assertNotIn("Inventario físico", source)
                self.assertNotIn("sm:grid-cols-3", source)
