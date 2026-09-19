from contextlib import ExitStack
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.security.models import AppModule
from apps.shared.module_sdk import ModuleManifest, PublicEntry
from apps.shared.module_sdk.services import public_directory_cards


def make_manifest(code, **overrides):
    values = {
        "code": code,
        "name": f"Servicio {code}",
        "description": f"Descripción de {code}.",
        "entry_url": f"{code}:dashboard",
        "default_enabled": True,
    }
    values.update(overrides)
    return ModuleManifest(**values)


def patched_discover(*manifests, providers=()):
    """Aísla el directorio de las apps realmente instaladas en el entorno."""
    stack = ExitStack()
    stack.enter_context(patch(
        "apps.shared.module_sdk.services.module_registry.discover",
        return_value=tuple(manifests),
    ))
    stack.enter_context(patch(
        "apps.shared.module_sdk.services.module_registry.public_entry_providers",
        return_value=tuple(providers),
    ))
    return stack


def make_entry(code="ciudadania", **overrides):
    values = {
        "code": code,
        "name": "Mi cuenta ciudadana",
        "description": "Crea tu cuenta.",
        "url": "https://ciudadano.example.gob.mx/cuenta/",
        "icon": "user-round",
    }
    values.update(overrides)
    return PublicEntry(**values)


class ManifestPublicEntryTests(SimpleTestCase):
    def test_entry_url_publico_defaults_to_empty(self):
        self.assertEqual(make_manifest("demo").entry_url_publico, "")

    def test_entry_url_publico_is_stripped_and_kept_verbatim(self):
        manifest = make_manifest(
            "demo", entry_url_publico="  https://tramites.example.gob.mx/  ",
        )
        self.assertEqual(manifest.entry_url_publico, "https://tramites.example.gob.mx/")


class ManifestPublicDescriptionTests(SimpleTestCase):
    def test_descripcion_publica_defaults_to_empty_and_is_stripped(self):
        self.assertEqual(make_manifest("demo").descripcion_publica, "")
        manifest = make_manifest("demo", descripcion_publica="  Texto  ")
        self.assertEqual(manifest.descripcion_publica, "Texto")


class PublicEntryContractTests(SimpleTestCase):
    def test_normalizes_code_and_url(self):
        entry = make_entry(code=" CIUDADANIA ", url="  /cuenta/  ")
        self.assertEqual((entry.code, entry.url), ("ciudadania", "/cuenta/"))

    def test_rejects_invalid_code(self):
        with self.assertRaises(ValueError):
            make_entry(code="  ")


class PublicDirectoryCardsTests(TestCase):
    def test_card_uses_descripcion_publica_when_present(self):
        manifest = make_manifest(
            "tramites", entry_url_publico="/x/", descripcion_publica="Para el ciudadano.",
        )
        with patched_discover(manifest):
            self.assertEqual(public_directory_cards()[0]["description"], "Para el ciudadano.")

    def test_card_falls_back_to_description_when_public_is_empty(self):
        manifest = make_manifest("tramites", entry_url_publico="/x/")
        with patched_discover(manifest):
            self.assertEqual(
                public_directory_cards()[0]["description"], "Descripción de tramites.",
            )

    def test_module_without_public_entry_is_not_listed(self):
        with patched_discover(make_manifest("interno")):
            self.assertEqual(public_directory_cards(), ())

    def test_module_with_public_entry_is_listed_with_url_verbatim(self):
        manifest = make_manifest(
            "tramites", entry_url_publico="https://tramites.example.gob.mx/catalogo/",
        )
        with patched_discover(manifest):
            cards = public_directory_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["code"], "tramites")
        self.assertEqual(cards[0]["url"], "https://tramites.example.gob.mx/catalogo/")

    def test_disabled_module_is_not_listed(self):
        manifest = make_manifest("tramites", entry_url_publico="/x/")
        AppModule.objects.create(slug="tramites", name="Trámites", is_active=False)
        with patched_discover(manifest):
            self.assertEqual(public_directory_cards(), ())

    def test_enabled_row_wins_over_default_disabled(self):
        manifest = make_manifest("tramites", entry_url_publico="/x/", default_enabled=False)
        AppModule.objects.create(slug="tramites", name="Trámites", is_active=True)
        with patched_discover(manifest):
            self.assertEqual(len(public_directory_cards()), 1)

    def test_without_row_falls_back_to_default_enabled(self):
        manifest = make_manifest("tramites", entry_url_publico="/x/", default_enabled=False)
        with patched_discover(manifest):
            self.assertEqual(public_directory_cards(), ())

    def test_unresolvable_staff_entry_does_not_hide_public_card(self):
        # entry_url apunta a una ruta de personal que no existe: no debe importar.
        manifest = make_manifest(
            "tramites", entry_url="no_existe:nunca", entry_url_publico="/x/",
        )
        with patched_discover(manifest):
            self.assertEqual(len(public_directory_cards()), 1)


class PublicEntryProviderTests(TestCase):
    def test_entry_without_appmodule_is_listed_and_creates_no_row(self):
        with patched_discover(providers=[("ciudadania", make_entry)]):
            cards = public_directory_cards()
        self.assertEqual([c["code"] for c in cards], ["ciudadania"])
        self.assertEqual(cards[0]["url"], "https://ciudadano.example.gob.mx/cuenta/")
        self.assertFalse(AppModule.objects.filter(slug="ciudadania").exists())

    def test_provider_returning_none_hides_entry(self):
        with patched_discover(providers=[("ciudadania", lambda: None)]):
            self.assertEqual(public_directory_cards(), ())

    def test_entry_with_empty_url_is_not_listed(self):
        with patched_discover(providers=[("ciudadania", lambda: make_entry(url=""))]):
            self.assertEqual(public_directory_cards(), ())

    def test_broken_provider_does_not_break_the_rest(self):
        def roto():
            raise RuntimeError("boom")

        manifest = make_manifest("tramites", entry_url_publico="/x/")
        with self.assertLogs("apps.shared.module_sdk.services", level="ERROR"):
            with patched_discover(manifest, providers=[("roto", roto), ("ok", make_entry)]):
                codes = [c["code"] for c in public_directory_cards()]
        self.assertEqual(codes, ["tramites", "ciudadania"])

    def test_provider_returning_wrong_type_is_ignored(self):
        with self.assertLogs("apps.shared.module_sdk.services", level="ERROR"):
            with patched_discover(providers=[("mal", lambda: {"url": "/x/"})]):
                self.assertEqual(public_directory_cards(), ())

    def test_module_card_wins_over_entry_with_same_code(self):
        manifest = make_manifest("ciudadania", entry_url_publico="/modulo/")
        with patched_discover(manifest, providers=[("ciudadania", make_entry)]):
            cards = public_directory_cards()
        self.assertEqual([c["url"] for c in cards], ["/modulo/"])


class PublicDirectoryViewTests(TestCase):
    def test_route_name_resolves_to_directorio(self):
        self.assertEqual(reverse("directorio_publico"), "/directorio/")

    def test_anonymous_user_gets_directory_without_login(self):
        manifest = make_manifest(
            "tramites", name="Trámites",
            entry_url_publico="https://tramites.example.gob.mx/",
        )
        with patched_discover(manifest):
            response = self.client.get("/directorio/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trámites")
        self.assertContains(response, 'href="https://tramites.example.gob.mx/"')
        self.assertNotContains(response, "Ingresar al Entorno")

    def test_view_lists_public_entry_next_to_modules(self):
        manifest = make_manifest(
            "tramites", name="Trámites", entry_url_publico="/t/",
        )
        with patched_discover(manifest, providers=[("ciudadania", make_entry)]):
            response = self.client.get("/directorio/")
        self.assertContains(response, "Mi cuenta ciudadana")
        self.assertContains(response, 'href="https://ciudadano.example.gob.mx/cuenta/"')
        self.assertContains(response, 'data-lucide="user-round"')

    def test_empty_directory_shows_message(self):
        with patched_discover(make_manifest("interno")):
            response = self.client.get("/directorio/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no hay servicios en línea")

    def test_staff_landing_is_untouched(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ingresar al Entorno")
