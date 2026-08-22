import uuid
from django.db import models


class Notification(models.Model):

    class Level(models.TextChoices):
        INFO = 'info',       'Info'
        SUCCESS = 'success',    'Success'
        WARNING = 'warning',    'Warning'
        DANGER = 'danger',     'Danger'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
    )
    recipient = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    actor = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        related_name='notifications_sent',
        null=True,
        blank=True,
    )
    message = models.TextField()
    url = models.CharField(max_length=500, blank=True)
    level = models.CharField(
        max_length=10,
        choices=Level.choices,
        default=Level.INFO,
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f'{self.recipient} — {self.message[:40]}'

    def get_icon(self):
        icon_map = {
            self.Level.INFO:    'fa-circle-info',
            self.Level.SUCCESS: 'fa-circle-check',
            self.Level.WARNING: 'fa-triangle-exclamation',
            self.Level.DANGER:  'fa-circle-exclamation',
        }
        return icon_map.get(self.level, 'fa-circle-info')


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def notify(recipient, message, url='', level=Notification.Level.INFO,
           actor=None, organization=None):
    """Create a single notification."""
    if recipient is None:
        return None
    return Notification.objects.create(
        recipient=recipient,
        message=message,
        url=url,
        level=level,
        actor=actor,
        organization=organization or getattr(recipient, 'organization', None),
    )


def notify_org_admins(organization, message, url='', level=Notification.Level.INFO,
                      actor=None):
    """
    Fan out a notification to every Agency Owner / Manager in the org.
    """
    from accounts.models import User

    if organization is None:
        return []

    admins = User.objects.filter(
        organization=organization,
        role__in=[User.Role.AGENCY_OWNER, User.Role.MANAGER],
        is_active=True,
    )

    created = [
        Notification(
            recipient=admin, message=message, url=url,
            level=level, actor=actor, organization=organization,
        )
        for admin in admins
    ]
    if created:
        Notification.objects.bulk_create(created)
    return created