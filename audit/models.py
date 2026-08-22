import uuid
from django.db import models


class AuditLog(models.Model):
    """
    Immutable record of a sensitive operation. Never updated or deleted
    through the application — corrections are new log entries.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='audit_logs',
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        related_name='audit_logs',
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=64)

    # Loose object reference (kept as strings so a deleted row's log survives).
    object_type = models.CharField(max_length=64, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)

    ip = models.CharField(max_length=45, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', '-created_at']),
            models.Index(fields=['action']),
            models.Index(fields=['object_type', 'object_id']),
        ]

    def __str__(self):
        who = self.actor.full_name if self.actor else 'system'
        return f'{self.action} by {who} @ {self.created_at:%Y-%m-%d %H:%M}'
