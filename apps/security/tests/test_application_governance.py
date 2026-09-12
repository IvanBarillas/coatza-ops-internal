from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.security.models import AppModule, UserAppRole
from apps.security.selectors.application_selectors import ApplicationGovernanceSelectors as Governance


@override_settings(AXENTRA_REQUIRE_VERIFIED_EMAIL=False, AXENTRA_REQUIRE_ADMIN_MFA=False, DEBUG=True, AXENTRA_CORE_VERBOSE_RADAR=False)
class ApplicationGovernanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.manager = User.objects.create_user(email="manager@example.test", is_manager=True)
        cls.owner = User.objects.create_user(email="owner@example.test")
        cls.viewer = User.objects.create_user(email="viewer@example.test")
        cls.inactive = User.objects.create_user(email="inactive@example.test", is_active=False)
        cls.deleted = User.objects.create_user(email="deleted@example.test", is_deleted=True)
        security, _ = AppModule.objects.get_or_create(slug="security", defaults={"name": "Seguridad"})
        for user in (cls.owner, cls.viewer):
            UserAppRole.objects.create(user=user, app=security, role="viewer", permissions_list=["has_access_module"])
        cls.apps = AppModule.objects.bulk_create([
            AppModule(slug=f"phase-app-{i:03}", name=f"Aplicación {i:03}") for i in range(100)
        ])
        UserAppRole.objects.create(user=cls.owner, app=cls.apps[0], role="owner")
        UserAppRole.objects.create(user=cls.owner, app=cls.apps[1], role="owner", is_deleted=True)
        UserAppRole.objects.create(user=cls.owner, app=cls.apps[2], role="owner", is_active=False)
        UserAppRole.objects.create(user=cls.inactive, app=cls.apps[3], role="owner")
        UserAppRole.objects.create(user=cls.deleted, app=cls.apps[4], role="owner")

    def test_overview_query_budget_is_constant_at_one_and_one_hundred_apps(self):
        for user in (self.owner, self.manager):
            with self.subTest(user=user.email), self.assertNumQueries(4):
                summary = Governance.overview(user)
                self.assertLessEqual(len(summary['resumen_apps']), 5)
        self.assertEqual(Governance.overview(self.owner)['total_apps_gobernadas'], 1)

    def test_scope_excludes_revoked_owners_and_inactive_apps(self):
        self.assertEqual(list(Governance.scope(self.owner)), [self.apps[0]])
        self.assertFalse(Governance.scope(self.inactive).exists())
        self.assertFalse(Governance.scope(self.deleted).exists())
        self.apps[0].is_active = False
        self.apps[0].save()
        self.assertFalse(Governance.scope(self.owner).exists())
        self.apps[0].is_active = True
        self.apps[0].is_deleted = True
        self.apps[0].save()
        self.assertFalse(Governance.scope(self.owner).exists())

    def test_counts_exclude_inactive_and_deleted_users_and_memberships(self):
        rows = {app.pk: app for app in Governance.with_counts(Governance.scope(self.manager))}
        self.assertEqual(rows[self.apps[0].pk].total_owners, 1)
        for app in self.apps[1:5]:
            self.assertEqual(rows[app.pk].total_usuarios, 0)
            self.assertEqual(rows[app.pk].total_owners, 0)

    def test_catalog_paginates_and_preserves_filters(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse('security:applications'), {'q': 'phase-app', 'owner': 'without', 'sort': '-name', 'page': 2})
        self.assertEqual(response.status_code, 200)
        page = response.context['page_obj']
        self.assertEqual(page.paginator.count, 99)
        self.assertEqual(len(page), 20)
        self.assertEqual(page.number, 2)
        self.assertContains(response, 'q=phase-app&amp;owner=without&amp;sort=-name&amp;page=3')

    def test_delegated_owner_cannot_search_outside_scope(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('security:applications'), {'q': self.apps[1].slug})
        self.assertEqual(response.context['page_obj'].paginator.count, 0)
        self.assertNotContains(response, self.apps[1].name)

    def test_viewer_without_ownership_sees_empty_catalog(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('security:applications'))
        self.assertEqual(response.context['page_obj'].paginator.count, 0)

    def test_direct_and_htmx_targets_and_bad_page(self):
        self.client.force_login(self.manager)
        for target, template in (
            ('', 'security/pages/applications.html'),
            ('workbench', 'security/workbench/applications_workbench.html'),
            ('page-content', 'security/content/applications_content.html'),
        ):
            with self.subTest(target=target):
                response = self.client.get(reverse('security:applications'), {'page': 'invalid', 'sort': 'bad', 'owner': 'bad'}, HTTP_HX_REQUEST='true', HTTP_HX_TARGET=target)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template)
                self.assertEqual(response.context['page_obj'].number, 1)
                self.assertEqual(response.context['sort'], 'name')

    def test_panel_is_bounded_and_links_to_catalog(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse('security:control_panel'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['resumen_apps']), 5)
        self.assertContains(response, reverse('security:applications'))
        self.assertNotContains(response, 'No se detectan alertas críticas')

    def test_anonymous_cannot_open_catalog(self):
        self.assertEqual(self.client.get(reverse('security:applications')).status_code, 302)

    def test_analytics_count_dynamic_apps_and_live_memberships(self):
        from apps.security.selectors.security_selectors import SecurityDashboardSelectors
        before = SecurityDashboardSelectors.obtener_metricas_firewall()
        AppModule.objects.create(name="Satélite nuevo", slug="phase-extra")
        after = SecurityDashboardSelectors.obtener_metricas_firewall()
        self.assertEqual(after['total_apps'], before['total_apps'] + 1)
        self.assertEqual(after['llaves_activas_db'], 3)  # Dos membresías Security y un owner.
        self.assertEqual(after['cuentas_riesgo'], 2)  # Usuario inactivo y usuario eliminado.

    def test_summary_counts_suspended_roles_without_deleted_memberships(self):
        totals = Governance.overview(self.manager)
        self.assertEqual(totals['total_roles_suspendidos'], 1)
        self.assertEqual(totals['total_owners'], 1)
        self.assertEqual(totals['total_usuarios_con_acceso'], 2)
