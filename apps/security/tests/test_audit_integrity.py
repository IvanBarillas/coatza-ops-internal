import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.security.middleware.audit import AuditTransactionMiddleware
from apps.security.models import SecurityAuditLog
from apps.security.services.audit_context import AuditWriteError, current_audit
from apps.security.utils.forensic_auditor import ForensicAuditor


class AuditIntegrityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='audit@example.test')
        self.request = RequestFactory().post('/', REMOTE_ADDR='192.0.2.9', HTTP_X_FORWARDED_FOR='203.0.113.12')
        self.request.user = self.user

    def record(self):
        return ForensicAuditor.registrar_evento(self.request, 'UPDATE', 'test', 'Prueba', 'Cuenta propia',
                                              payload={'before': {'is_active': True}, 'after': {'is_active': False}})

    def test_correlation_generated_server_side_and_context_reset(self):
        self.request.META['HTTP_X_REQUEST_ID'] = 'untrusted'
        def view(request):
            self.record()
            self.record()
            return HttpResponse('ok')
        response = AuditTransactionMiddleware(view)(self.request)
        identifier = uuid.UUID(response['X-Request-ID'])
        self.assertEqual(SecurityAuditLog.objects.filter(correlation_id=identifier).count(), 2)
        self.assertIsNone(current_audit.get())

    def test_ip_does_not_trust_forwarded_header(self):
        self.assertEqual(self.record().ip_address, '192.0.2.9')

    def test_recursive_secret_redaction_preserves_before_after(self):
        event = SecurityAuditLog.objects.create(operator_user=self.user, target_scope='test', payload_json={
            'password': 'never-store', 'nested': [{'Authorization': 'secret', 'active': True}],
            'before': {'role': 'viewer'}, 'after': {'role': 'editor'},
        })
        event.refresh_from_db()
        self.assertNotIn('never-store', str(event.payload_json))
        self.assertEqual(event.payload_json['nested'][0]['Authorization'], '[REDACTADO]')
        self.assertEqual(event.payload_json['after']['role'], 'editor')

    def test_system_actor_and_missing_actor(self):
        event = SecurityAuditLog.objects.create(system_actor='backup-monitor', target_scope='instancia')
        self.assertIn('backup-monitor', str(event))
        with self.assertRaises(ValidationError):
            SecurityAuditLog.objects.create(target_scope='sin actor')

    def test_existing_event_cannot_be_saved_over(self):
        event = self.record()
        event.action_name = 'alterado'
        with self.assertRaises(ValidationError):
            event.save()
        event.refresh_from_db()
        self.assertEqual(event.action_name, 'Prueba')

    def test_swallowed_audit_failure_rolls_back_business_change(self):
        def view(request):
            self.user.first_name = 'No debe persistir'
            self.user.save()
            try:
                self.record()
            except AuditWriteError:
                pass  # Simula un servicio heredado que oculta el fallo.
            return HttpResponse('éxito aparente')
        with patch.object(SecurityAuditLog, '_save_table', side_effect=OperationalError('sensitive database detail')):
            response = AuditTransactionMiddleware(view)(self.request)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'sensitive', response.content)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')

    def test_success_commits_change_and_evidence_together(self):
        def view(request):
            self.user.first_name = 'Persistido'
            self.user.save()
            self.record()
            return HttpResponse('ok')
        self.assertEqual(AuditTransactionMiddleware(view)(self.request).status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Persistido')
        self.assertEqual(SecurityAuditLog.objects.count(), 1)

    def test_forbidden_response_does_not_erase_security_attempt_tracking(self):
        def view(request):
            self.record()
            return HttpResponse(status=403)
        AuditTransactionMiddleware(view)(self.request)
        self.assertEqual(SecurityAuditLog.objects.count(), 1)

    def test_snapshot_uses_explicit_fields_and_normalizes_uuid(self):
        from apps.security.services.audit_snapshots import snapshot
        value = snapshot(self.user, ['id', 'is_active', 'password'])
        self.assertEqual(value['id'], str(self.user.pk))
        self.assertEqual(value['password'], '[REDACTADO]')
        self.assertNotIn('email', value)

    def test_health_check_reports_dependencies_without_secrets(self):
        from io import StringIO
        from django.core.management import call_command
        output = StringIO()
        call_command('check_operational_health', stdout=output)
        self.assertIn('"database": true', output.getvalue())
        self.assertIn('"cache": true', output.getvalue())

    def test_failed_health_check_has_nonzero_result_and_redacted_error(self):
        from io import StringIO
        from django.core.management import call_command, CommandError
        output = StringIO()
        with patch('apps.security.management.commands.check_operational_health.cache.get', side_effect=RuntimeError('secret-in-error')):
            with self.assertRaises(CommandError):
                call_command('check_operational_health', stdout=output)
        self.assertIn('"cache": false', output.getvalue())
        self.assertNotIn('secret-in-error', output.getvalue())
