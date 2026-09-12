from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.security.middleware.sessions import SESSION_ID, auth_digest
from apps.security.models import AccountSession, SecurityAuditLog


@override_settings(AXENTRA_REQUIRE_VERIFIED_EMAIL=False, AXENTRA_REQUIRE_ADMIN_MFA=False,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AccountSessionTests(TestCase):
    password = 'Sesiones-seguras-92!'

    def setUp(self):
        self.user = get_user_model().objects.create_user(email='sessions@example.test', password=self.password)
        self.url = reverse('accounts:sessions')
        self.client.force_login(self.user)
        self.other = Client()
        self.other.force_login(self.user)
        self.other.get(self.url, REMOTE_ADDR='192.0.2.10', HTTP_USER_AGENT='Otro navegador')
        self.other_id = self.other.session[SESSION_ID]

    def test_inventory_private_metadata_and_no_cookie(self):
        response = self.client.get(self.url, REMOTE_ADDR='192.0.2.15', HTTP_X_FORWARDED_FOR='203.0.113.8', HTTP_USER_AGENT='<script>alert(1)</script>')
        self.assertContains(response, 'Otro navegador')
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, self.client.session.session_key)
        current = AccountSession.objects.get(pk=self.client.session[SESSION_ID])
        self.assertEqual(current.ip_address, '192.0.2.15')
        self.assertIn('no-store', response['Cache-Control'])

    def test_individual_revocation_and_htmx_enforcement(self):
        response = self.client.post(self.url, {'session': self.other_id, 'password': self.password})
        self.assertEqual(response.status_code, 302)
        response = self.other.get(self.url, HTTP_HX_REQUEST='true')
        self.assertEqual(response['HX-Redirect'], reverse('accounts:login'))
        self.assertNotIn('_auth_user_id', self.other.session)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(SecurityAuditLog.objects.filter(module_component='sessions').count(), 1)

    def test_other_user_id_cannot_be_revoked_or_seen(self):
        stranger = get_user_model().objects.create_user(email='stranger@example.test', password=self.password)
        session = AccountSession.objects.get(pk=self.other_id)
        session.user = stranger
        session.user_agent = 'Secreto de otra cuenta'
        session.save()
        self.assertNotContains(self.client.get(self.url), session.user_agent)
        self.assertEqual(self.client.post(self.url, {'session': session.pk, 'password': self.password}).status_code, 404)
        session.refresh_from_db()
        self.assertIsNone(session.revoked_at)

    def test_wrong_password_and_get_do_not_revoke(self):
        self.client.get(self.url, {'session': self.other_id})
        response = self.client.post(self.url, {'session': self.other_id, 'password': 'incorrecta'})
        self.assertContains(response, 'Contraseña incorrecta')
        self.assertIsNone(AccountSession.objects.get(pk=self.other_id).revoked_at)

    def test_all_others_includes_untracked_session_and_keeps_current(self):
        untracked = Client()
        untracked.force_login(self.user)
        self.client.post(self.url, {'action': 'others', 'password': self.password})
        self.assertEqual(self.client.get(self.url).status_code, 200)
        for client in (self.other, untracked):
            self.assertEqual(client.get(self.url).status_code, 302)
            self.assertNotIn('_auth_user_id', client.session)

    def test_current_revocation_logs_out(self):
        self.client.get(self.url)
        self.client.post(self.url, {'session': self.client.session[SESSION_ID], 'password': self.password})
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_cookie_rotation_preserves_record(self):
        self.client.get(self.url)
        identifier = self.client.session[SESSION_ID]
        session = self.client.session
        session.cycle_key()
        self.client.cookies['sessionid'] = session.session_key
        self.client.get(self.url)
        self.assertEqual(self.client.session[SESSION_ID], identifier)
        self.assertEqual(AccountSession.objects.filter(user=self.user).count(), 2)

    def test_missing_record_fails_closed(self):
        AccountSession.objects.filter(pk=self.other_id).delete()
        self.assertEqual(self.other.get(self.url).status_code, 302)
        self.assertNotIn('_auth_user_id', self.other.session)

    def test_logout_revokes_record(self):
        self.other.post(reverse('accounts:logout'))
        self.assertIsNotNone(AccountSession.objects.get(pk=self.other_id).revoked_at)

    def test_password_change_preserves_inventory_and_excludes_old_sessions(self):
        self.client.get(self.url)
        identifier = self.client.session[SESSION_ID]
        self.client.post(reverse('accounts:password_change'), {
            'old_password': self.password, 'new_password1': 'Cambio-seguro-98!', 'new_password2': 'Cambio-seguro-98!',
        })
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[SESSION_ID], identifier)
        self.assertEqual(response.context['sessions'].paginator.count, 1)

    def test_pagination_expiry_and_invalid_ip(self):
        now = timezone.now()
        AccountSession.objects.bulk_create([AccountSession(user=self.user, auth_digest=auth_digest(self.user), last_seen_at=now, expires_at=now + timedelta(days=1)) for _ in range(25)])
        AccountSession.objects.filter(pk=self.other_id).update(expires_at=now-timedelta(seconds=1))
        response = self.client.get(self.url, REMOTE_ADDR='invalid')
        self.assertEqual(len(response.context['sessions']), 20)
        self.assertEqual(response.context['sessions'].paginator.count, 26)
        self.assertIsNone(AccountSession.objects.get(pk=self.client.session[SESSION_ID]).ip_address)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, {'action': 'others', 'password': self.password}).status_code, 403)
