"""Excepciones explícitas al aislamiento de datos por dependencia."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.shared.models import AxentraBaseModel


class DepartmentAccessGrant(AxentraBaseModel):
    membership = models.ForeignKey('security.UserAppRole', on_delete=models.PROTECT, related_name='department_grants')
    source_department = models.ForeignKey('security.Dependencia', on_delete=models.PROTECT, related_name='outgoing_access_grants')
    target_department = models.ForeignKey('security.Dependencia', on_delete=models.PROTECT, related_name='incoming_access_grants')
    permission = models.CharField(max_length=100, help_text='Llave fina exacta del manifiesto; sin comodines.')
    reason = models.TextField(help_text='Motivo de la autorización excepcional.')
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='issued_department_grants', editable=False)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['membership', 'source_department', 'target_department', 'permission'], name='uq_department_access_grant'),
        ]
        verbose_name = 'Autorización entre dependencias'
        verbose_name_plural = 'Autorizaciones entre dependencias'

    def clean(self):
        from apps.security.services.permission_loader import get_app_permissions
        if self.source_department_id == self.target_department_id:
            raise ValidationError('La dependencia de destino debe ser diferente a la de origen.')
        if not self.reason.strip():
            raise ValidationError({'reason': 'Indique el motivo de la autorización.'})
        if self.membership_id:
            declared = get_app_permissions(self.membership.app.slug)['permissions']
            if self.permission not in declared or self.permission == 'has_access_module':
                raise ValidationError({'permission': 'Seleccione una operación fina declarada en el módulo.'})

    def __str__(self):
        return f'{self.membership} → {self.target_department} ({self.permission})'
