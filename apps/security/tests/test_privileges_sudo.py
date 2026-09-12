import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.admin.sites import site
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.security.decorators import axentra_module_gate
from apps.security.middleware.sessions import auth_digest
from apps.security.middleware.sudo import SUDO_KEY, sudo_required
from apps.security.models import AppModule, UserAppRole, SecurityAuditLog
from apps.security.services.permission_loader import get_user_permissions_for_app
from apps.shared.context_processors import user_module_permissions
from apps.shared.module_sdk.services import user_can_open_module


@override_settings(AXENTRA_REQUIRE_VERIFIED_EMAIL=False, AXENTRA_REQUIRE_ADMIN_MFA=False,
                   AXENTRA_CORE_VERBOSE_RADAR=False,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PrivilegeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='technical@example.test', password='Tecnico-83!', is_manager=True)
        self.module = AppModule.objects.get(slug='accounts')

    def request(self):
        request = RequestFactory().get('/', HTTP_HX_REQUEST='true')
        request.user = self.user
        return request

    def gate(self):
        return axentra_module_gate('accounts', 'can_view_list')(lambda request: HttpResponse('operación'))(self.request())

    def test_technical_admin_governs_security_but_has_no_functional_bypass(self):
        self.assertTrue(get_user_permissions_for_app(self.user, 'security')['can_modify_matrix'])
        self.assertFalse(get_user_permissions_for_app(self.user, 'accounts')['has_access_module'])
        self.assertFalse(user_can_open_module(self.user, 'accounts'))
        self.assertEqual(self.gate().status_code, 403)

    def test_superuser_also_requires_functional_membership(self):
        self.user.is_superuser = True
        self.user.save()
        self.assertEqual(self.gate().status_code, 403)

    def test_explicit_fine_permission_required_and_revocable(self):
        membership = UserAppRole.objects.create(user=self.user, app=self.module, role='viewer', permissions_list=['has_access_module'])
        self.assertEqual(self.gate().status_code, 403)
        membership.permissions_list.append('can_view_list')
        membership.save()
        self.assertEqual(self.gate().status_code, 200)
        membership.is_active = False
        membership.save()
        self.assertEqual(self.gate().status_code, 403)

    def test_navigation_does_not_advertise_ungranted_functional_apps(self):
        modules = user_module_permissions(self.request())['allowed_modules']
        self.assertIn('security', modules)
        self.assertNotIn('accounts', modules)
        self.assertNotIn('organigrama', modules)

    def test_functional_owner_does_not_gain_platform_authority(self):
        self.user.is_manager = False
        self.user.save()
        UserAppRole.objects.create(user=self.user, app=self.module, role='owner')
        self.assertEqual(self.gate().status_code, 200)
        self.assertFalse(get_user_permissions_for_app(self.user, 'security')['has_access_module'])

    def test_unknown_module_fails_closed_for_technical_admin(self):
        view = axentra_module_gate('uninstalled')(lambda request: HttpResponse('incorrecto'))
        self.assertEqual(view(self.request()).status_code, 503)

    def test_inactive_admin_has_no_permissions_or_navigation(self):
        self.user.is_active = False
        self.user.save()
        self.assertFalse(get_user_permissions_for_app(self.user, 'security')['has_access_module'])
        self.assertEqual(user_module_permissions(self.request())['allowed_modules'], [])

    def test_staff_cannot_promote_accounts_using_django_admin(self):
        self.user.is_staff = True
        request = self.request()
        with patch.object(self.user, 'has_perm', return_value=True):
            self.assertFalse(site._registry[get_user_model()].has_change_permission(request, self.user))
            self.assertFalse(site._registry[get_user_model()].has_add_permission(request))

    def test_privilege_flag_change_invalidates_existing_sessions(self):
        self.client.force_login(self.user)
        self.user.is_manager = False
        self.user.save(update_fields=['is_manager'])
        self.assertEqual(self.client.get(reverse('accounts:account_security')).status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    @override_settings(AXENTRA_REQUIRE_ADMIN_MFA=True)
    def test_functional_admin_must_enroll_totp(self):
        self.user.is_manager = False
        self.user.save()
        UserAppRole.objects.create(user=self.user, app=self.module, role='admin')
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(reverse('accounts:account_security')), reverse('accounts:mfa_setup'), fetch_redirect_response=False)

    def test_technical_admin_does_not_bypass_department_capabilities(self):
        from apps.shared.utils.dependency_capabilities import AxentraCapabilityOrchestrator
        result = AxentraCapabilityOrchestrator.obtener_estatus_capacidad(self.user, 'accounts')
        self.assertFalse(result['can_authorize'])
        self.assertFalse(result['can_operate'])

    def test_capabilities_follow_explicit_department_and_active_structure(self):
        from apps.security.models import Dependencia, Sede, AreaOperativa, UserProfile, AppDependencyCapability
        from apps.shared.utils.dependency_capabilities import AxentraCapabilityOrchestrator
        dep = Dependencia.objects.create(nombre='Dependencia')
        area = AreaOperativa.objects.create(nombre='Área', dependencia=dep, sede_fisica=Sede.objects.create(nombre='Sede'))
        UserProfile.objects.create(user=self.user, area=area)
        AppDependencyCapability.objects.create(app=self.module, dependencia=dep, can_operate=True, can_authorize=False)
        result = AxentraCapabilityOrchestrator.obtener_estatus_capacidad(self.user, 'accounts')
        self.assertTrue(result['can_operate'])
        self.assertFalse(result['can_authorize'])
        dep.is_active = False
        dep.save()
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.assertFalse(AxentraCapabilityOrchestrator.obtener_estatus_capacidad(self.user, 'accounts')['can_operate'])


@override_settings(AXENTRA_REQUIRE_VERIFIED_EMAIL=False, AXENTRA_REQUIRE_ADMIN_MFA=False,
                   AXENTRA_CORE_VERBOSE_RADAR=False,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SudoTests(TestCase):
    password = 'Confirmacion-segura-83!'

    def setUp(self):
        self.user = get_user_model().objects.create_user(email='sudo@example.test', password=self.password)
        self.client.force_login(self.user)
        self.url = reverse('accounts:sudo')
        self.mutation = reverse('module_toggle', args=['accounts'])

    def test_mutation_blocked_before_view_and_not_replayed(self):
        with patch('core.views.set_module_enabled') as service:
            response = self.client.post(self.mutation, {'enabled': '0'}, HTTP_REFERER='http://testserver/index/')
            self.assertRedirects(response, self.url, fetch_redirect_response=False)
            service.assert_not_called()
            response = self.client.post(self.url, {'password': self.password})
            self.assertRedirects(response, '/index/', fetch_redirect_response=False)
            service.assert_not_called()

    def test_htmx_challenge_and_foreign_return_url_rejected(self):
        response = self.client.post(self.mutation, HTTP_HX_REQUEST='true', HTTP_REFERER='https://evil.test/steal')
        self.assertEqual(response['HX-Redirect'], self.url)
        self.assertEqual(self.client.session['axentra_sudo_return'], reverse('index_hub'))

    def test_wrong_password_does_not_establish_sudo(self):
        self.client.post(self.url, {'password': 'incorrecta'})
        self.assertNotIn(SUDO_KEY, self.client.session)

    def test_success_does_not_grant_authority(self):
        self.client.post(self.url, {'password': self.password})
        self.client.post(self.mutation, {'enabled': '0'})
        self.assertTrue(AppModule.objects.get(slug='accounts').is_active)
        self.assertEqual(SecurityAuditLog.objects.filter(module_component='sudo').count(), 1)

    def test_timeout_future_and_malformed_proof_fail_closed(self):
        self.client.post(self.url, {'password': self.password})
        for stamp in (time.time()-301, time.time()+60, 'invalid'):
            session = self.client.session
            session[SUDO_KEY] = {'at': stamp, 'auth': auth_digest(self.user), 'device': None}
            session.save()
            self.assertRedirects(self.client.post(self.mutation), self.url, fetch_redirect_response=False)

    def test_sudo_not_shared_with_other_session(self):
        self.client.post(self.url, {'password': self.password})
        other = Client()
        other.force_login(self.user)
        self.assertRedirects(other.post(self.mutation), self.url, fetch_redirect_response=False)

    def test_password_change_invalidates_sudo_but_not_current_login(self):
        self.client.post(self.url, {'password': self.password})
        self.client.post(reverse('accounts:password_change'), {
            'old_password': self.password, 'new_password1': 'Cambio-completo-95!', 'new_password2': 'Cambio-completo-95!',
        })
        self.assertRedirects(self.client.post(self.mutation), self.url, fetch_redirect_response=False)

    def test_new_totp_required_even_with_verified_session_and_replay_rejected(self):
        device = TOTPDevice.objects.create(user=self.user, confirmed=True)
        session = self.client.session
        session['otp_device_id'] = device.persistent_id
        session.save()
        self.client.post(self.url, {'password': self.password})
        self.assertNotIn(SUDO_KEY, self.client.session)
        device.refresh_from_db()
        device.throttle_reset(commit=True)
        code = str(totp(device.bin_key))
        self.client.post(self.url, {'password': self.password, 'token': code})
        self.assertIn(SUDO_KEY, self.client.session)
        self.client.post(self.url, {'password': self.password, 'token': code})
        self.assertNotIn(SUDO_KEY, self.client.session)

    def test_admin_and_accounts_mutations_require_sudo(self):
        for path in (reverse('admin:security_user_add'), reverse('accounts:funcionario_create')):
            self.assertRedirects(self.client.post(path), self.url, fetch_redirect_response=False)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, {'password': self.password}).status_code, 403)

    def test_satellite_decorator_does_not_block_reads(self):
        request = RequestFactory().get('/')
        request.user = self.user
        request.session = self.client.session
        view = sudo_required(lambda request: HttpResponse('lectura'))
        self.assertEqual(view(request).status_code, 200)
        request.method = 'POST'
        self.assertEqual(view(request).status_code, 302)

    def test_authorized_admin_can_mutate_after_reauthentication(self):
        from apps.shared.module_sdk import ModuleManifest
        self.user.is_manager = True
        self.user.save()
        self.client.force_login(self.user)
        self.client.post(self.url, {'password': self.password})
        module = AppModule.objects.create(slug='demo_sudo', name='Demo', is_active=False)
        manifest = ModuleManifest(code='demo_sudo', name='Demo', description='Test', entry_url='index_hub', can_disable=True)
        with patch('apps.shared.module_sdk.services.module_registry.get', return_value=manifest):
            self.client.post(reverse('module_toggle', args=['demo_sudo']), {'enabled': '1'})
        module.refresh_from_db()
        self.assertTrue(module.is_active)
        self.assertTrue(SecurityAuditLog.objects.filter(module_component='MODULE_SDK').exists())

    @override_settings(AXENTRA_REQUIRE_ADMIN_MFA=True)
    def test_step_up_requires_enrollment_for_custom_functional_roles(self):
        self.assertRedirects(self.client.get(self.url), reverse('accounts:mfa_setup'), fetch_redirect_response=False)
