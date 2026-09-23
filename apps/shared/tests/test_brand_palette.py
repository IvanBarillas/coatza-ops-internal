import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.security.models import AppModule, TenantConfig, UserAppRole
from apps.shared.branding import DEFAULT_BRAND_COLORS
from apps.shared.context_processors import global_tenant_settings

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
LEGACY_PALETTE = ("#6B1D2F", "#4A5568")


class BrandPaletteTests(TestCase):
    def test_default_palette_is_valid_hex(self):
        self.assertEqual(set(DEFAULT_BRAND_COLORS), {"primary", "secondary", "accent"})
        for value in DEFAULT_BRAND_COLORS.values():
            self.assertRegex(value, HEX)

    def test_model_defaults_come_from_central_palette(self):
        for role in ("primary", "secondary", "accent"):
            field = TenantConfig._meta.get_field(f"{role}_color")
            self.assertEqual(field.default, DEFAULT_BRAND_COLORS[role])

    def test_context_processor_exposes_brand_defaults(self):
        context = global_tenant_settings(RequestFactory().get("/"))
        self.assertEqual(context["brand_defaults"], DEFAULT_BRAND_COLORS)

    def test_templates_do_not_hardcode_legacy_palette(self):
        roots = [Path(settings.BASE_DIR) / "templates", Path(settings.BASE_DIR) / "apps"]
        offenders = []
        for root in roots:
            for path in root.rglob("*.html"):
                text = path.read_text(encoding="utf-8").upper()
                if any(color in text for color in LEGACY_PALETTE):
                    offenders.append(str(path))
        self.assertEqual(offenders, [])


@override_settings(
    AXENTRA_REQUIRE_VERIFIED_EMAIL=False,
    AXENTRA_REQUIRE_ADMIN_MFA=False,
    AXENTRA_CORE_VERBOSE_RADAR=False,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class TenantConfigPaletteFormTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            email="paleta@example.test", password="Confirmacion-segura-83!"
        )
        UserAppRole.objects.create(
            user=user,
            app=AppModule.objects.get(slug="configuration"),
            role="configuration_manager",
            permissions_list=["has_access_module", "can_view_configuration"],
        )
        self.client.force_login(user)

    def test_form_offers_restore_and_undo_with_axentra_palette(self):
        response = self.client.get(reverse("security:tenant_config"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Restaurar Axentra", html)
        self.assertIn("Deshacer cambios", html)
        for value in DEFAULT_BRAND_COLORS.values():
            self.assertIn(f"'{value}'", html)
