import uuid
from django.db import models


def tenant_number_default():
    """Generates a temporary placeholder — real number assigned in save()."""
    return 'TEN-PENDING'


class Tenant(models.Model):

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE',     'Active'
        INACTIVE = 'INACTIVE',   'Inactive'
        BLACKLISTED = 'BLACKLISTED', 'Blacklisted'

    # ── Identity ──────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.PROTECT,
        related_name='tenants'
    )
    tenant_number = models.CharField(
        max_length=20, unique=True, editable=False)
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    national_id = models.CharField(max_length=50, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # ── Emergency Contact ─────────────────────────────────
    emergency_contact = models.CharField(max_length=255, blank=True)
    emergency_phone = models.CharField(max_length=20, blank=True)
    emergency_relation = models.CharField(max_length=100, blank=True)

    # ── Address ───────────────────────────────────────────
    address = models.TextField(blank=True)

    # ── Portal ────────────────────────────────────────────
    user = models.OneToOneField(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tenant_profile'
    )

    # ── Documents ─────────────────────────────────────────
    id_document = models.FileField(
        upload_to='tenants/documents/',
        blank=True,
        null=True
    )
    photo = models.ImageField(
        upload_to='tenants/photos/',
        blank=True,
        null=True
    )

    # ── Status ────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    notes = models.TextField(blank=True)

    # ── Timestamps ────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tenant'
        verbose_name_plural = 'Tenants'
        ordering = ['full_name']

    def __str__(self):
        return f'{self.tenant_number} — {self.full_name}'

    def save(self, *args, **kwargs):
        if not self.tenant_number or self.tenant_number == 'TEN-PENDING':
            self.tenant_number = self._generate_tenant_number()
        super().save(*args, **kwargs)

    def _generate_tenant_number(self):
        """
        Generates a sequential tenant number.
        Format: TEN-000001
        """
        last = Tenant.objects.order_by('-created_at').first()
        if last and last.tenant_number.startswith('TEN-'):
            try:
                last_num = int(last.tenant_number.split('-')[1])
                return f'TEN-{str(last_num + 1).zfill(6)}'
            except (ValueError, IndexError):
                pass
        return 'TEN-000001'

    def get_active_tenancy(self):
        return self.tenancies.filter(status='ACTIVE').first()

    def get_current_unit(self):
        tenancy = self.get_active_tenancy()
        return tenancy.unit if tenancy else None

    def get_current_property(self):
        tenancy = self.get_active_tenancy()
        return tenancy.unit.prop if tenancy else None

    def get_status_badge(self):
        badge_map = {
            self.Status.ACTIVE:      'rw-badge-success',
            self.Status.INACTIVE:    'rw-badge-dark',
            self.Status.BLACKLISTED: 'rw-badge-danger',
        }
        return badge_map.get(self.status, 'rw-badge-dark')
