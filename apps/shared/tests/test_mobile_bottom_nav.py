from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse


class BottomNavAssetTests(SimpleTestCase):
    def test_controller_is_discoverable_and_covers_htmx_lifecycle(self):
        path = finders.find("js/axentra-bottom-nav.js")
        self.assertTrue(path)
        with open(path, encoding="utf-8") as asset:
            source = asset.read()
        for token in (
            "htmx:pushedIntoHistory",
            "htmx:historyRestore",
            "htmx:beforeRequest",
            "popstate",
            "aria-current",
            "AxentraBottomNav",
        ):
            self.assertIn(token, source)


class BottomNavTemplateTests(TestCase):
    def render_nav(self, modules=("security", "accounts", "organigrama", "configuration")):
        request = RequestFactory().get("/index/")
        User = get_user_model()
        request.user = User.objects.filter(email="nav@example.test").first() or User.objects.create_user(
            email="nav@example.test", password="Confirmacion-segura-83!"
        )
        context = {
            "allowed_modules": list(modules),
            "satellite_navigation": [],
            "modulo_actual": "security",
        }
        return render_to_string("components/app_bottom_nav.html", context, request=request)

    def test_panel_tab_requires_security_module(self):
        with_security = self.render_nav()
        self.assertIn("Panel", with_security)
        self.assertIn("grid-cols-4", with_security)

        without_security = self.render_nav(modules=("configuration",))
        self.assertNotIn("Panel", without_security)
        self.assertNotIn("/app/security/control/", without_security)
        self.assertIn("grid-cols-3", without_security)
        self.assertIn("--modules-x: 50vw", without_security)

    def test_users_without_modules_get_no_modules_tab_or_sheet(self):
        html = self.render_nav(modules=())
        self.assertNotIn("data-modules-toggle", html)
        self.assertNotIn("mobile-modules-sheet", html)
        self.assertNotIn("Panel", html)
        self.assertIn("grid-cols-2", html)

    def test_profile_tab_links_to_account_page_without_htmx(self):
        html = self.render_nav()
        marker = 'href="/app/auth/account/security/"'
        self.assertIn(marker, html)
        anchor = html[html.index(marker):html.index("Perfil")]
        self.assertNotIn("hx-get", anchor)

    def test_tabs_carry_path_data_for_client_side_state(self):
        html = self.render_nav()
        self.assertIn("data-bottom-nav", html)
        self.assertIn('data-bottom-nav-path="/index/"', html)
        self.assertIn('data-bottom-nav-match="prefix"', html)

    def test_modules_tab_opens_a_sheet_with_expanded_groups(self):
        html = self.render_nav()
        self.assertIn("data-modules-toggle", html)
        self.assertIn('id="mobile-modules-sheet"', html)
        self.assertIn("Organización", html)
        self.assertIn("Identidad Institucional", html)
        self.assertNotIn("openMenu === 'admin'", html)

    def test_shell_loads_the_controller(self):
        self.assertIn("axentra-bottom-nav.js", open("templates/shell/base.html", encoding="utf-8").read())


@override_settings(
    AXENTRA_REQUIRE_VERIFIED_EMAIL=False,
    AXENTRA_REQUIRE_ADMIN_MFA=False,
    AXENTRA_CORE_VERBOSE_RADAR=False,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class HubHtmxTargetTests(TestCase):
    """Inicio del nav móvil pide el hub con destino #workbench."""

    def setUp(self):
        user = get_user_model().objects.create_user(
            email="hub@example.test", password="Confirmacion-segura-83!"
        )
        self.client.force_login(user)
        self.url = reverse("index_hub")

    def get_hub(self, target=None):
        headers = {"HTTP_HX_REQUEST": "true"}
        if target:
            headers["HTTP_HX_TARGET"] = target
        return self.client.get(self.url, **headers)

    def test_workbench_target_keeps_scroll_container_and_footer(self):
        html = self.get_hub("workbench").content.decode()
        self.assertIn('id="page-content"', html)
        self.assertIn("<footer", html)
        self.assertIn('id="launcher-content"', html)
        self.assertNotIn("<html", html)

    def test_page_content_target_returns_only_the_inner_content(self):
        html = self.get_hub("page-content").content.decode()
        self.assertIn('id="launcher-content"', html)
        self.assertNotIn('id="page-content"', html)

    def test_launcher_search_still_gets_only_the_fragment(self):
        html = self.get_hub("launcher-content").content.decode()
        self.assertTrue(html.lstrip().startswith('<div id="launcher-content"'))
        self.assertNotIn('id="page-content"', html)

    def test_full_page_is_unchanged(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn("<html", html)
        self.assertEqual(html.count('id="page-content"'), 1)
