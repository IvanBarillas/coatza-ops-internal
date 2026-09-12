"""Configuración de dominios de producción aislada del entorno real."""
import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class MunicipalProductionSettingsTests(SimpleTestCase):
    def test_each_installation_uses_only_its_configured_csrf_origins(self):
        for origins, expected in (
            ('https://municipio-a.example, https://portal-a.example, ',
             ['https://municipio-a.example', 'https://portal-a.example']),
            ('https://municipio-b.example', ['https://municipio-b.example']),
            ('', []),
        ):
            environment = {
                **os.environ,
                'DJANGO_ENV': 'build',
                'SECRET_KEY': 'test-only-never-production',
                'ALLOWED_HOSTS': 'municipio.example',
                'DATABASE_URL': 'sqlite:///:memory:',
                'EMAIL_HOST': 'localhost',
                'EMAIL_HOST_USER': '',
                'EMAIL_HOST_PASSWORD': '',
                'CSRF_TRUSTED_ORIGINS': origins,
            }
            code = (
                'from core.settings import production as config; '
                f'assert config.CSRF_TRUSTED_ORIGINS == {expected!r}; '
                'assert config.DEBUG is False; '
                'assert config.SESSION_COOKIE_SECURE; '
                'assert config.CSRF_COOKIE_SECURE'
            )
            with self.subTest(origins=origins):
                result = subprocess.run(
                    [sys.executable, '-c', code], cwd=settings.BASE_DIR,
                    env=environment, capture_output=True, text=True, timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
