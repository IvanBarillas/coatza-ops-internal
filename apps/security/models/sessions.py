import uuid

from django.conf import settings
from django.db import models


class AccountSession(models.Model):
    """Inventario revocable. Nunca almacena la cookie ni la llave de Django."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='account_sessions')
    auth_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=500, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_seen_at', '-id']
        indexes = [models.Index(fields=['user', 'revoked_at'], name='account_session_user_state')]
