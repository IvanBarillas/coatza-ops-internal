"""Superficies de los satélites en una instalación real: API, dominios y entorno."""
import os
import subprocess
import sys
from unittest.mock import patch

from django.conf import settings
from django.core.checks import Error, Warning
from django.test import SimpleTestCase, TestCase, override_settings

from apps.shared.checks import check_installation_surfaces
from apps.shared.module_sdk import ModuleManifest
from apps.shared.module_sdk.routing import satellite_urlpatterns

ENTORNO_PROPIO = (
    "AXENTRA_EXTRA_APPS", "AXENTRA_HOST_URLCONFS", "INTERNAL_API_KEY", "SECURE_REDIRECT_EXEMPT",
)


def manifest(code="demo", **overrides):
    values = {"code": code, "name": code, "description": code, "entry_url": "index_hub"}
    values.update(overrides)
    return ModuleManifest(**values)


class ManifestApiFieldsTests(SimpleTestCase):
    def test_api_is_optional_and_off_by_default(self):
        m = manifest()
        self.assertEqual((m.api_urlconf, m.api_prefix), ("", "api/v1/"))

    def test_prefix_is_normalized(self):
        for raw in ("/api/v1", "api/v1/", " /api/v1/ "):
            with self.subTest(raw=raw):
                self.assertEqual(manifest(api_urlconf="x.y", api_prefix=raw).api_prefix, "api/v1/")

    def test_api_urlconf_requires_a_prefix(self):
        with self.assertRaises(ValueError):
            manifest(api_urlconf="x.y", api_prefix="/")


class SatelliteUrlpatternsTests(SimpleTestCase):
    def patterns_for(self, *manifests):
        with patch("apps.shared.module_sdk.routing.module_registry.discover", return_value=manifests):
            return satellite_urlpatterns()

    def test_api_is_mounted_next_to_the_dashboard(self):
        patterns = self.patterns_for(manifest(
            urlconf="apps.shared.tests.urls_host_fake", url_prefix="app/demo/",
            api_urlconf="apps.shared.tests.urls_api_fake",
        ))
        self.assertEqual([str(p.pattern) for p in patterns], ["app/demo/", "api/v1/"])

    def test_module_without_api_mounts_no_api(self):
        patterns = self.patterns_for(manifest(urlconf="apps.shared.tests.urls_host_fake", url_prefix="app/demo/"))
        self.assertEqual([str(p.pattern) for p in patterns], ["app/demo/"])

    def test_two_satellites_can_share_the_api_prefix(self):
        patterns = self.patterns_for(
            manifest("a", api_urlconf="apps.shared.tests.urls_api_fake"),
            manifest("b", api_urlconf="apps.shared.tests.urls_api_fake"),
        )
        self.assertEqual([str(p.pattern) for p in patterns], ["api/v1/", "api/v1/"])


class HostUrlconfMiddlewareTests(TestCase):
    hosts = {"publico.test": "apps.shared.tests.urls_host_fake"}

    @override_settings(AXENTRA_HOST_URLCONFS=hosts, ALLOWED_HOSTS=["publico.test", "otro.test", "testserver"])
    def test_mapped_host_uses_its_urlconf(self):
        response = self.client.get("/", HTTP_HOST="publico.test")
        self.assertEqual(response.content, b"superficie-publica")

    @override_settings(AXENTRA_HOST_URLCONFS=hosts, ALLOWED_HOSTS=["publico.test", "otro.test", "testserver"])
    def test_port_and_case_do_not_matter(self):
        response = self.client.get("/", HTTP_HOST="PUBLICO.test:8443")
        self.assertEqual(response.content, b"superficie-publica")

    @override_settings(AXENTRA_HOST_URLCONFS=hosts, ALLOWED_HOSTS=["publico.test", "otro.test", "testserver"])
    def test_unmapped_host_keeps_the_root_urlconf(self):
        response = self.client.get("/", HTTP_HOST="otro.test")
        self.assertNotEqual(response.content, b"superficie-publica")

    @override_settings(AXENTRA_HOST_URLCONFS={})
    def test_without_mapping_nothing_changes(self):
        response = self.client.get("/", HTTP_HOST="testserver")
        self.assertNotEqual(response.content, b"superficie-publica")

    @override_settings(AXENTRA_HOST_URLCONFS=hosts, ALLOWED_HOSTS=["publico.test", "testserver"])
    def test_public_host_does_not_serve_staff_routes(self):
        response = self.client.get("/directorio/", HTTP_HOST="publico.test")
        self.assertEqual(response.status_code, 404)


class InstallationChecksTests(SimpleTestCase):
    def ids(self):
        return [issue.id for issue in check_installation_surfaces(None)]

    @override_settings(AXENTRA_HOST_URLCONFS={}, INTERNAL_API_KEY="")
    def test_clean_without_configuration(self):
        self.assertEqual(self.ids(), [])

    @override_settings(AXENTRA_HOST_URLCONFS={"publico.test": "no.existe.urls"}, ALLOWED_HOSTS=["publico.test"])
    def test_unimportable_urlconf_is_an_error(self):
        issues = check_installation_surfaces(None)
        self.assertEqual([i.id for i in issues], ["axentra.E001"])
        self.assertIsInstance(issues[0], Error)

    @override_settings(AXENTRA_HOST_URLCONFS={"publico.test": "apps.shared.tests.urls_host_fake"}, ALLOWED_HOSTS=["otro.test"])
    def test_host_outside_allowed_hosts_is_a_warning(self):
        issues = check_installation_surfaces(None)
        self.assertEqual([i.id for i in issues], ["axentra.W001"])
        self.assertIsInstance(issues[0], Warning)

    @override_settings(AXENTRA_HOST_URLCONFS={}, INTERNAL_API_KEY="")
    def test_api_without_key_is_a_warning(self):
        with patch("apps.shared.module_sdk.registry.module_registry.discover",
                   return_value=(manifest(api_urlconf="apps.shared.tests.urls_api_fake"),)):
            self.assertEqual(self.ids(), ["axentra.W002"])

    @override_settings(AXENTRA_HOST_URLCONFS={}, INTERNAL_API_KEY="una-llave")
    def test_api_with_key_is_clean(self):
        with patch("apps.shared.module_sdk.registry.module_registry.discover",
                   return_value=(manifest(api_urlconf="apps.shared.tests.urls_api_fake"),)):
            self.assertEqual(self.ids(), [])


class EnvironmentSettingsTests(SimpleTestCase):
    """Los ajustes se leen del entorno al importar: se prueban en un proceso aparte."""

    def run_settings(self, code, module="core.settings.base", **env):
        environment = {k: v for k, v in os.environ.items() if k not in ENTORNO_PROPIO and not k.endswith("_PUBLIC_BASE_URL")}
        environment.update({
            "DJANGO_ENV": "build", "SECRET_KEY": "solo-para-pruebas", "ALLOWED_HOSTS": "x.example",
            "DATABASE_URL": "sqlite:///:memory:", "EMAIL_HOST": "localhost",
            "EMAIL_HOST_USER": "", "EMAIL_HOST_PASSWORD": "", **env,
        })
        return subprocess.run(
            [sys.executable, "-c", f"import importlib; c = importlib.import_module({module!r}); {code}"],
            cwd=settings.BASE_DIR, env=environment, capture_output=True, text=True, timeout=30,
        )

    def test_defaults_keep_the_core_standalone(self):
        result = self.run_settings(
            "assert c.AXENTRA_EXTRA_APPS == []; assert c.INSTALLED_APPS[-1] == 'apps.security.apps.SecurityConfig'; "
            "assert c.AXENTRA_HOST_URLCONFS == {}; assert c.INTERNAL_API_KEY == ''; "
            "assert not any(n.endswith('_PUBLIC_BASE_URL') for n in dir(c))"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_extra_apps_come_from_the_environment_after_the_core_apps(self):
        result = self.run_settings(
            "assert c.INSTALLED_APPS[-2:] == ['django_quill', 'ciudadania'], c.INSTALLED_APPS[-3:]",
            AXENTRA_EXTRA_APPS=" django_quill , ciudadania,, apps.shared.apps.SharedConfig ",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_api_key_and_public_base_urls_come_from_the_environment(self):
        result = self.run_settings(
            "assert c.INTERNAL_API_KEY == 'llave'; "
            "assert c.TRAMITES_PUBLIC_BASE_URL == 'https://c.example/tramites'; "
            "assert c.CIUDADANIA_PUBLIC_BASE_URL == 'https://c.example/ciudadano'; "
            "assert not hasattr(c, 'NO_ES_PUBLIC_BASE')",
            INTERNAL_API_KEY="llave", TRAMITES_PUBLIC_BASE_URL="https://c.example/tramites",
            CIUDADANIA_PUBLIC_BASE_URL="https://c.example/ciudadano", NO_ES_PUBLIC_BASE="x",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_host_urlconfs_are_parsed(self):
        result = self.run_settings(
            "assert c.AXENTRA_HOST_URLCONFS == {'a.example': 'core.urls_publico', 'b.example': 'x.y'}",
            AXENTRA_HOST_URLCONFS=" A.example = core.urls_publico , b.example=x.y ,",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_malformed_host_urlconfs_fail_fast(self):
        result = self.run_settings("pass", AXENTRA_HOST_URLCONFS="a.example")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AXENTRA_HOST_URLCONFS", result.stderr)

    def test_production_redirect_exempt_is_opt_in(self):
        default = self.run_settings("assert c.SECURE_REDIRECT_EXEMPT == []", module="core.settings.production")
        self.assertEqual(default.returncode, 0, default.stderr)
        exempt = self.run_settings(
            "assert c.SECURE_REDIRECT_EXEMPT == ['^api/v1/']; assert c.SECURE_SSL_REDIRECT",
            module="core.settings.production", SECURE_REDIRECT_EXEMPT="^api/v1/",
        )
        self.assertEqual(exempt.returncode, 0, exempt.stderr)


# ── Superficie pública (segunda entrega) ─────────────────────────────────────
import importlib
from types import SimpleNamespace

from django.urls import clear_url_caches

from apps.shared.module_sdk import PublicSurface
from apps.shared.module_sdk.registry import ModuleRegistry
from apps.shared.module_sdk.routing import public_urlpatterns


class PublicSurfaceContractTests(SimpleTestCase):
    def test_manifest_public_surface_is_optional(self):
        m = manifest()
        self.assertEqual((m.public_urlconf, m.public_prefix), ("", ""))

    def test_public_prefix_is_normalized_and_required(self):
        self.assertEqual(manifest(public_urlconf="x.y", public_prefix="/tramites").public_prefix, "tramites/")
        with self.assertRaises(ValueError):
            manifest(public_urlconf="x.y")
        with self.assertRaises(ValueError):
            PublicSurface("x", "x.y", "/")


class RegistryPublicSurfacesTests(SimpleTestCase):
    def registry_with(self, manifests=(), modules=()):
        registry = ModuleRegistry()
        registry.discover = lambda force=False: tuple(manifests)
        registry._public_entry_modules = tuple(modules)
        return registry

    def test_surface_from_a_manifest(self):
        registry = self.registry_with(manifests=[manifest("tramites", public_urlconf="p.urls", public_prefix="tramites")])
        self.assertEqual(registry.public_surfaces(), (PublicSurface("tramites", "p.urls", "tramites/"),))

    def test_surface_from_a_package_without_panel_uses_static_constants(self):
        module = SimpleNamespace(PUBLIC_URLCONF="ciudadania.urls", PUBLIC_PREFIX="ciudadano/")
        registry = self.registry_with(modules=[("ciudadania", module)])
        self.assertEqual(registry.public_surfaces(), (PublicSurface("ciudadania", "ciudadania.urls", "ciudadano/"),))

    def test_public_entry_without_constants_mounts_nothing(self):
        registry = self.registry_with(modules=[("ciudadania", SimpleNamespace(get_public_entry=lambda: None))])
        self.assertEqual(registry.public_surfaces(), ())

    def test_manifest_wins_over_a_package_with_the_same_code(self):
        module = SimpleNamespace(PUBLIC_URLCONF="viejo.urls", PUBLIC_PREFIX="viejo/")
        registry = self.registry_with(
            manifests=[manifest("ciudadania", public_urlconf="nuevo.urls", public_prefix="nuevo")],
            modules=[("ciudadania", module)],
        )
        self.assertEqual(registry.public_surfaces(), (PublicSurface("ciudadania", "nuevo.urls", "nuevo/"),))

    def test_public_urlpatterns_use_each_prefix(self):
        surfaces = (PublicSurface("a", "apps.shared.tests.urls_publico_fake", "a/"),)
        with patch("apps.shared.module_sdk.routing.module_registry.public_surfaces", return_value=surfaces):
            self.assertEqual([str(p.pattern) for p in public_urlpatterns()], ["a/"])


class PublicHostIntegrationTests(TestCase):
    """El dominio ciudadano sirve el directorio y las vistas públicas, y nada del personal."""

    hosts = {"ciudadano.test": "core.urls_publico"}

    def setUp(self):
        import core.urls_publico

        def recargar_urlconf():
            importlib.reload(core.urls_publico)
            clear_url_caches()

        # LIFO: primero se deja de parchear y después se recarga el urlconf real.
        self.addCleanup(recargar_urlconf)
        surfaces = (PublicSurface("demo", "apps.shared.tests.urls_publico_fake", "demo/"),)
        patcher = patch("apps.shared.module_sdk.routing.module_registry.public_surfaces", return_value=surfaces)
        patcher.start()
        self.addCleanup(patcher.stop)
        recargar_urlconf()
        override = override_settings(
            AXENTRA_HOST_URLCONFS=self.hosts, ALLOWED_HOSTS=["ciudadano.test", "digital.test", "testserver"]
        )
        override.enable()
        self.addCleanup(override.disable)

    def get(self, path, host="ciudadano.test"):
        return self.client.get(path, HTTP_HOST=host)

    def test_satellite_public_views_are_served_under_their_prefix(self):
        response = self.get("/demo/hola/")
        self.assertEqual((response.status_code, response.content), (200, b"hola-publico"))

    def test_root_and_directory_are_public(self):
        self.assertEqual(self.get("/").status_code, 200)
        self.assertEqual(self.get("/directorio/").status_code, 200)

    def test_staff_surface_is_not_reachable_from_the_public_host(self):
        for path in ("/index/", "/app/", "/api/v1/tramites/buscar"):
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 404)

    def test_public_views_are_not_served_from_the_staff_host(self):
        self.assertEqual(self.get("/demo/hola/", host="digital.test").status_code, 404)


class PublicPrefixCheckTests(SimpleTestCase):
    @override_settings(AXENTRA_HOST_URLCONFS={}, INTERNAL_API_KEY="k")
    def test_duplicated_public_prefix_is_an_error(self):
        surfaces = (PublicSurface("a", "x.urls", "p/"), PublicSurface("b", "y.urls", "p/"))
        with patch("apps.shared.module_sdk.registry.module_registry.public_surfaces", return_value=surfaces):
            self.assertEqual([i.id for i in check_installation_surfaces(None)], ["axentra.E003"])
