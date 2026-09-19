from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.security.models import AppModule
from apps.shared.module_sdk import ModuleManifest
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


def patched_discover(*manifests):
    return patch(
        "apps.shared.module_sdk.services.module_registry.discover",
        return_value=tuple(manifests),
    )


class ManifestPublicEntryTests(SimpleTestCase):
    def test_entry_url_publico_defaults_to_empty(self):
        self.assertEqual(make_manifest("demo").entry_url_publico, "")

    def test_entry_url_publico_is_stripped_and_kept_verbatim(self):
        manifest = make_manifest(
            "demo", entry_url_publico="  https://tramites.example.gob.mx/  ",
        )
        self.assertEqual(manifest.entry_url_publico, "https://tramites.example.gob.mx/")


class PublicDirectoryCardsTests(TestCase):
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

    def test_empty_directory_shows_message(self):
        with patched_discover(make_manifest("interno")):
            response = self.client.get("/directorio/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no hay servicios en línea")

    def test_staff_landing_is_untouched(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ingresar al Entorno")
