from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.security.models import AppModule, SecurityAuditLog, TenantConfig, UserAppRole


@override_settings(
    AXENTRA_REQUIRE_VERIFIED_EMAIL=False,
    AXENTRA_REQUIRE_ADMIN_MFA=False,
    AXENTRA_CORE_VERBOSE_RADAR=False,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class PrivacidadCookiesTests(TestCase):
    """privacidad_cookies_view — misma mecánica que tenant_config_view
    (mismo Singleton, mismo permiso can_configure_tenant), pero es una
    sección hermana propia dentro de Configuración, no una cuarta
    pestaña de Identidad Institucional. Ver docs/apps/
    public-municipal-portal.md para el porqué (fuente única de verdad
    legal para toda la instalación, en vez de un aviso de privacidad
    duplicado por satélite)."""

    password = "Confirmacion-segura-83!"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="privacidad@example.test", password=self.password
        )
        self.client.force_login(self.user)
        self.module = AppModule.objects.get(slug="configuration")
        self.sudo_url = reverse("accounts:sudo")
        self.url = reverse("security:privacidad_cookies")

    def _conceder_permiso_configuracion(self, *permisos):
        UserAppRole.objects.create(
            user=self.user,
            app=self.module,
            role="configuration_manager",
            permissions_list=["has_access_module", *permisos],
        )

    def _establecer_sudo_fresco(self):
        self.client.post(self.sudo_url, {"password": self.password})

    def test_requiere_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertNotEqual(response.status_code, 200)

    def test_ver_requiere_can_view_configuration(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("index_hub"), fetch_redirect_response=False)

        self._conceder_permiso_configuracion("can_view_configuration")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_mutacion_sin_sudo_fresco_es_desafiada(self):
        self._conceder_permiso_configuracion(
            "can_view_configuration", "can_configure_tenant"
        )
        response = self.client.post(self.url, {"aviso_privacidad": "Texto nuevo"})
        self.assertRedirects(response, self.sudo_url, fetch_redirect_response=False)

    def test_guardar_sin_can_configure_tenant_no_modifica_nada(self):
        self._conceder_permiso_configuracion("can_view_configuration")
        self._establecer_sudo_fresco()

        original = TenantConfig.objects.first()
        original_aviso = original.aviso_privacidad if original else ""

        self.client.post(self.url, {"aviso_privacidad": "Intento no autorizado"})

        actual = TenantConfig.objects.first()
        self.assertEqual(actual.aviso_privacidad, original_aviso)

    def test_guardar_con_permiso_y_sudo_persiste_y_audita(self):
        self._conceder_permiso_configuracion(
            "can_view_configuration", "can_configure_tenant"
        )
        self._establecer_sudo_fresco()

        response = self.client.post(
            self.url,
            {
                "aviso_privacidad": "Este es el aviso de privacidad institucional.",
                "politica_cookies": "Esta es la política de cookies institucional.",
            },
        )
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

        config = TenantConfig.objects.first()
        self.assertEqual(
            config.aviso_privacidad,
            "Este es el aviso de privacidad institucional.",
        )
        self.assertEqual(
            config.politica_cookies,
            "Esta es la política de cookies institucional.",
        )

        self.assertTrue(
            SecurityAuditLog.objects.filter(
                action_name="RECONFIGURACION_PRIVACIDAD_COOKIES",
                level_status=SecurityAuditLog.Levels.CRITICAL,
            ).exists()
        )

    def test_una_sola_fuente_de_verdad_el_singleton_no_se_duplica(self):
        self._conceder_permiso_configuracion(
            "can_view_configuration", "can_configure_tenant"
        )
        self._establecer_sudo_fresco()

        self.client.post(self.url, {"aviso_privacidad": "Primero"})
        self.client.post(self.url, {"aviso_privacidad": "Segundo"})

        self.assertEqual(TenantConfig.objects.count(), 1)
        self.assertEqual(TenantConfig.objects.first().aviso_privacidad, "Segundo")
