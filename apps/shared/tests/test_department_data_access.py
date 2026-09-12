from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.security.models import (
    AppModule, AreaOperativa, DepartmentAccessGrant, Dependencia,
    Sede, UserAppRole, UserProfile,
)
from apps.shared.module_sdk.data_access import authorized_departments, scope_queryset


@override_settings(AXENTRA_REQUIRE_VERIFIED_EMAIL=False, AXENTRA_REQUIRE_ADMIN_MFA=False, AXENTRA_CORE_VERBOSE_RADAR=False)
class DepartmentDataAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(email='scope@example.test')
        cls.admin = User.objects.create_superuser(email='grant@example.test')
        cls.app, _ = AppModule.objects.get_or_create(slug='security', defaults={'name': 'Security'})
        cls.source = Dependencia.objects.create(nombre='Origen')
        cls.target = Dependencia.objects.create(nombre='Destino', parent=cls.source)
        cls.site = Sede.objects.create(nombre='Sede')
        cls.own = AreaOperativa.objects.create(nombre='Oficina origen', dependencia=cls.source, sede_fisica=cls.site)
        cls.other = AreaOperativa.objects.create(nombre='Oficina destino', dependencia=cls.target, sede_fisica=cls.site)
        cls.profile = UserProfile.objects.create(user=cls.user, area=cls.own)
        cls.membership = UserAppRole.objects.create(user=cls.user, app=cls.app, role='viewer', permissions_list=['has_access_module', 'can_view_matrix'])

    def queryset(self, user=None, permission='can_view_matrix'):
        return scope_queryset(AreaOperativa.objects.all(), user or self.user, app_slug='security', permission=permission)

    def grant(self, **kwargs):
        return DepartmentAccessGrant.objects.create(
            membership=self.membership, source_department=self.source,
            target_department=self.target, permission='can_view_matrix',
            reason='Revisión autorizada', granted_by=self.admin, **kwargs,
        )

    def test_default_has_no_hierarchy_inheritance(self):
        self.assertEqual(list(self.queryset()), [self.own])
        with self.assertRaises(Http404):
            get_object_or_404(self.queryset(), pk=self.other.pk)

    def test_export_uses_same_scope(self):
        self.assertEqual(list(self.queryset().values_list('pk', flat=True)), [self.own.pk])

    def test_explicit_grant_is_scoped_to_operation(self):
        self.grant()
        self.assertCountEqual(self.queryset(), [self.own, self.other])
        self.assertFalse(self.queryset(permission='can_modify_matrix').exists())

    def test_revocation_and_expiry(self):
        grant = self.grant()
        for changes in ({'is_active': False}, {'is_active': True, 'is_deleted': True}, {'is_deleted': False, 'expires_at': timezone.now() - timedelta(seconds=1)}):
            for field, value in changes.items():
                setattr(grant, field, value)
            grant.save()
            self.assertEqual(list(self.queryset()), [self.own])

    def test_transfer_invalidates_previous_exception(self):
        self.grant()
        third = Dependencia.objects.create(nombre='Otra adscripción')
        office = AreaOperativa.objects.create(nombre='Otra oficina', dependencia=third, sede_fisica=self.site)
        self.profile.area = office
        self.profile.save()
        self.assertEqual(list(self.queryset()), [office])

    def test_inactive_and_deleted_users_are_denied(self):
        for field in ('is_active', 'is_deleted'):
            setattr(self.user, field, field == 'is_deleted')
            self.assertFalse(self.queryset().exists())
            self.user.is_active = True
            self.user.is_deleted = False
        self.assertFalse(self.queryset(user=AnonymousUser()).exists())

    def test_revoked_membership_is_denied_even_with_grant(self):
        self.grant()
        self.membership.is_active = False
        self.membership.save()
        self.assertFalse(self.queryset().exists())

    def test_disabled_app_is_denied(self):
        self.app.is_active = False
        self.app.save()
        self.assertFalse(self.queryset().exists())

    def test_manager_does_not_bypass_data_scope(self):
        self.user.is_manager = True
        self.user.is_superuser = True
        self.assertEqual(list(self.queryset()), [self.own])
        self.assertFalse(self.queryset(user=self.admin).exists())

    def test_missing_or_inactive_profile_is_denied(self):
        self.profile.is_active = False
        self.profile.save()
        self.assertFalse(self.queryset().exists())

    def test_deleted_target_is_denied_despite_grant(self):
        self.grant()
        self.target.is_deleted = True
        self.target.save()
        self.assertEqual(list(self.queryset()), [self.own])

    def test_unknown_module_and_permission_deny(self):
        self.assertFalse(authorized_departments(self.user, app_slug='absent', permission='read').exists())
        self.assertFalse(self.queryset(permission='*').exists())

    def test_grant_requires_declared_operation_and_reason(self):
        grant = self.grant()
        grant.permission = '*'
        with self.assertRaises(ValidationError):
            grant.full_clean()
        grant.permission = 'can_view_matrix'
        grant.reason = ' '
        with self.assertRaises(ValidationError):
            grant.full_clean()

    def test_only_superuser_can_manage_exception_in_admin(self):
        from django.contrib.admin.sites import site
        from django.test import RequestFactory
        admin = site._registry[DepartmentAccessGrant]
        request = RequestFactory().get('/')
        request.user = self.user
        self.user.is_manager = True
        self.assertFalse(admin.has_add_permission(request))
        request.user = self.admin
        self.assertTrue(admin.has_add_permission(request))
        self.assertFalse(admin.has_delete_permission(request))

    @override_settings(DEBUG=True)
    def test_admin_records_author_and_change_log(self):
        from django.contrib.admin.models import LogEntry
        from django.urls import reverse
        self.client.force_login(self.admin)
        # Esta prueba verifica el grant; SUDO se cubre en su suite dedicada.
        import time
        from apps.security.middleware.sessions import auth_digest
        session = self.client.session
        session['axentra_sudo'] = {'at': time.time(), 'auth': auth_digest(self.admin), 'device': None}
        session.save()
        response = self.client.post(reverse('admin:security_departmentaccessgrant_add'), {
            'membership': str(self.membership.pk),
            'source_department': str(self.source.pk),
            'target_department': str(self.target.pk),
            'permission': 'can_view_matrix',
            'reason': 'Autorización de revisión',
            'is_active': 'on',
            '_save': 'Guardar',
        })
        self.assertEqual(response.status_code, 302)
        grant = DepartmentAccessGrant.objects.get(membership=self.membership)
        self.assertEqual(grant.granted_by, self.admin)
        self.assertTrue(LogEntry.objects.filter(user=self.admin, object_id=str(grant.pk)).exists())
