import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice


@override_settings(AXENTRA_REQUIRE_VERIFIED_EMAIL=False, DEBUG=True, AXENTRA_CORE_VERBOSE_RADAR=False, AXENTRA_REQUIRE_ADMIN_MFA=True,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class IdentityLifecycleTests(TestCase):
    password = 'Inicio-institucional-83!'
    new_password = 'Nueva-personal-91!Seguro'

    def setUp(self):
        self.user = get_user_model().objects.create_user(email='identity@example.test', password=self.password)
        self.client.force_login(self.user)

    def admin(self):
        self.user.is_manager = True
        self.user.save()
        self.client.force_login(self.user)

    def device(self):
        return TOTPDevice.objects.create(user=self.user, name='Axentra', confirmed=True)

    def verified(self, device):
        session = self.client.session
        session['otp_device_id'] = device.persistent_id
        session.save()

    def test_initial_password_blocks_post_and_htmx_and_allows_logout(self):
        self.user.must_change_password = True
        self.user.save()
        response = self.client.post(reverse('index_hub'), HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Redirect'], reverse('accounts:password_change'))
        self.assertEqual(self.client.get(reverse('accounts:password_change')).status_code, 200)
        self.assertEqual(self.client.post(reverse('accounts:logout')).status_code, 302)

    def test_password_change_keeps_current_session_and_revokes_others(self):
        other = Client()
        other.force_login(self.user)
        self.user.must_change_password = True
        self.user.save()
        response = self.client.post(reverse('accounts:password_change'), {
            'old_password': self.password, 'new_password1': self.new_password,
            'new_password2': self.new_password,
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password(self.new_password))
        self.assertIn('_auth_user_id', self.client.session)
        response = other.get(reverse('accounts:account_security'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', other.session)

    def test_same_or_wrong_old_password_does_not_clear_requirement(self):
        self.user.must_change_password = True
        self.user.save()
        for old in (self.password, 'incorrecta'):
            response = self.client.post(reverse('accounts:password_change'), {
                'old_password': old, 'new_password1': self.password, 'new_password2': self.password,
            })
            self.assertEqual(response.status_code, 200)
            self.user.refresh_from_db()
            self.assertTrue(self.user.must_change_password)

    def test_soft_deleted_user_is_logged_out_and_cannot_login(self):
        self.user.is_deleted = True
        self.user.save()
        self.client.get(reverse('accounts:account_security'))
        self.assertNotIn('_auth_user_id', self.client.session)
        response = self.client.post(reverse('accounts:login'), {'username': self.user.email, 'password': self.password})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_reactivation_does_not_restore_old_session(self):
        self.user.is_active = False
        self.user.save()
        self.user.is_active = True
        self.user.save()
        self.client.get(reverse('accounts:account_security'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_admin_without_device_must_enroll_including_admin_url(self):
        self.admin()
        for path in (reverse('index_hub'), reverse('admin:index')):
            self.assertRedirects(self.client.get(path), reverse('accounts:mfa_setup'), fetch_redirect_response=False)

    def test_existing_mfa_is_required_before_password_change(self):
        self.admin()
        self.device()
        self.user.must_change_password = True
        self.user.save()
        response = self.client.get(reverse('accounts:password_change'), HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Redirect'], reverse('accounts:mfa_verify'))

    def test_new_admin_changes_initial_password_before_enrollment(self):
        self.admin()
        self.user.must_change_password = True
        self.user.save()
        self.assertRedirects(self.client.get(reverse('accounts:mfa_setup')), reverse('accounts:password_change'), fetch_redirect_response=False)

    def enroll(self):
        self.client.post(reverse('accounts:mfa_setup'), {'action': 'start', 'password': self.password})
        device = TOTPDevice.objects.get(user=self.user, confirmed=False)
        response = self.client.post(reverse('accounts:mfa_setup'), {'action': 'confirm', 'token': str(totp(device.bin_key))})
        return device, response

    def test_enrollment_requires_proof_and_shows_recovery_codes_once(self):
        self.admin()
        response = self.client.get(reverse('accounts:mfa_setup'))
        self.assertIsNone(response.context['secret'])
        device, response = self.enroll()
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertEqual(len(response.context['recovery_codes']), 10)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(self.client.get(reverse('accounts:mfa_setup')).status_code, 302)

    def test_totp_cannot_be_replayed_and_is_throttled(self):
        device = self.device()
        other = Client()
        other.force_login(self.user)
        code = str(totp(device.bin_key))
        self.assertEqual(self.client.post(reverse('accounts:mfa_verify'), {'token': code}).status_code, 302)
        self.assertEqual(other.post(reverse('accounts:mfa_verify'), {'token': code}).status_code, 200)
        self.assertNotIn('otp_device_id', other.session)
        device.refresh_from_db()
        self.assertGreater(device.throttling_failure_count, 0)

    def test_recovery_is_single_use_and_can_replace_device(self):
        _, response = self.enroll()
        code = response.context['recovery_codes'][0]
        self.client.post(reverse('accounts:logout'))
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('accounts:mfa_verify'), {'recovery': 'on', 'token': code}).status_code, 302)
        self.assertFalse(StaticDevice.objects.get(user=self.user).token_set.filter(token=code).exists())
        self.assertEqual(self.client.post(reverse('accounts:mfa_replace'), {'password': self.password}).status_code, 302)
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())
        self.assertFalse(StaticDevice.objects.filter(user=self.user).exists())

    def test_unverified_session_cannot_replace_authenticator(self):
        self.device()
        self.assertRedirects(self.client.post(reverse('accounts:mfa_replace'), {'password': self.password}), reverse('accounts:mfa_verify'), fetch_redirect_response=False)
        self.assertTrue(TOTPDevice.objects.filter(user=self.user).exists())

    def test_otp_secrets_not_exposed_by_admin(self):
        from django.contrib.admin import site
        self.assertFalse(site.is_registered(TOTPDevice))
        self.assertFalse(site.is_registered(StaticDevice))

    def send_verification(self):
        self.client.post(reverse('accounts:email_verify'))
        return re.search(r'http://testserver([^\s]+)', mail.outbox[-1].body).group(1)

    def test_email_link_requires_post_and_is_single_use(self):
        path = self.send_verification()
        self.assertEqual(self.client.get(path).status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_email_verified)
        self.assertEqual(self.client.post(path).status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)
        self.assertEqual(self.client.post(path).status_code, 400)

    def test_email_token_is_bound_to_user_email_and_time(self):
        path = self.send_verification()
        other_user = get_user_model().objects.create_user(email='other@example.test')
        other = Client()
        other.force_login(other_user)
        self.assertEqual(other.post(path).status_code, 400)
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp() + 1801):
            self.assertEqual(self.client.post(path).status_code, 400)
        self.user.email = 'changed@example.test'
        self.user.save()
        self.assertEqual(self.client.post(path).status_code, 400)

    def test_resend_is_limited_in_database(self):
        self.send_verification()
        self.client.post(reverse('accounts:email_verify'))
        self.assertEqual(len(mail.outbox), 1)

    def test_csrf_required_for_mfa_and_session_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for name in ('mfa_setup', 'email_verify'):
            self.assertEqual(client.post(reverse('accounts:' + name)).status_code, 403)

    @override_settings(AXENTRA_REQUIRE_VERIFIED_EMAIL=True)
    def test_unverified_email_blocks_functional_views_but_can_confirm(self):
        response = self.client.get(reverse('accounts:account_security'), HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Redirect'], reverse('accounts:email_verify'))
        path = self.send_verification()
        self.assertEqual(self.client.post(path).status_code, 302)
        self.assertEqual(self.client.get(reverse('accounts:account_security')).status_code, 200)

    def test_initial_password_forms_reject_weak_credentials(self):
        from apps.security.forms.accounts_forms import CustomUserCreationForm, StaffUserCreationForm
        for form_class in (CustomUserCreationForm, StaffUserCreationForm):
            form = form_class(data={'email': 'new@example.test', 'first_name': 'Nuevo', 'password': '123'})
            self.assertFalse(form.is_valid())
            self.assertIn('password', form.errors)
