from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.security.models import AppModule, UserAppRole
from apps.shared.module_sdk.registry import module_registry


@override_settings(
    AXENTRA_OWNER_EMAIL="owner@municipio.test",
    AXENTRA_OWNER_DEFAULT_PASSWORD="Password-Seguro-2026!",
)
class BootstrapAxentraOwnerTests(TestCase):
    def test_creates_one_owner_with_membership_for_every_module(self):
        call_command("bootstrap_axentra_owner", stdout=StringIO())

        User = get_user_model()
        owner = User.objects.get(email="owner@municipio.test")
        self.assertTrue(owner.is_superuser)
        self.assertTrue(owner.is_manager)
        self.assertTrue(owner.check_password("Password-Seguro-2026!"))

        installed_codes = {item.code for item in module_registry.discover()}
        membership_codes = set(
            UserAppRole.objects.filter(
                user=owner,
                role=UserAppRole.ReservedRoles.OWNER,
            ).values_list("app__slug", flat=True)
        )
        self.assertEqual(membership_codes, installed_codes)

    def test_is_idempotent_and_preserves_existing_password(self):
        call_command("bootstrap_axentra_owner", stdout=StringIO())
        owner = get_user_model().objects.get(email="owner@municipio.test")
        owner.set_password("Password-Cambiado-Por-Usuario!")
        owner.save(update_fields=["password"])

        call_command("bootstrap_axentra_owner", stdout=StringIO())
        owner.refresh_from_db()

        self.assertTrue(owner.check_password("Password-Cambiado-Por-Usuario!"))
        self.assertEqual(
            UserAppRole.objects.filter(user=owner).count(),
            AppModule.objects.filter(is_deleted=False).count(),
        )

    def test_reset_mfa_removes_devices_and_invalidates_sessions(self):
        call_command("bootstrap_axentra_owner", stdout=StringIO())
        owner = get_user_model().objects.get(email="owner@municipio.test")
        previous_session_version = owner.session_version

        totp = TOTPDevice.objects.create(user=owner, name="Axentra", confirmed=True)
        recovery = StaticDevice.objects.create(user=owner, name="Axentra recovery", confirmed=True)
        StaticToken.objects.create(device=recovery, token="unicocodigo")

        out = StringIO()
        call_command("bootstrap_axentra_owner", "--reset-mfa", stdout=out)

        self.assertFalse(TOTPDevice.objects.filter(pk=totp.pk).exists())
        self.assertFalse(StaticDevice.objects.filter(pk=recovery.pk).exists())
        self.assertFalse(StaticToken.objects.filter(device=recovery).exists())

        owner.refresh_from_db()
        self.assertNotEqual(owner.session_version, previous_session_version)
        self.assertIn("MFA restablecido", out.getvalue())

    def test_reset_mfa_without_devices_reports_nothing_to_remove(self):
        call_command("bootstrap_axentra_owner", stdout=StringIO())

        out = StringIO()
        call_command("bootstrap_axentra_owner", "--reset-mfa", stdout=out)

        self.assertIn("no tenía MFA configurado", out.getvalue())

    def test_reset_mfa_on_fresh_owner_is_a_noop(self):
        out = StringIO()
        call_command("bootstrap_axentra_owner", "--reset-mfa", stdout=out)

        self.assertIn("--reset-mfa ignorado", out.getvalue())
