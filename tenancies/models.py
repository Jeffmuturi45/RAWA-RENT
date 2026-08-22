import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


class Tenancy(models.Model):

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE',      'Active'
        TRANSFERRED = 'TRANSFERRED', 'Transferred'
        ENDED = 'ENDED',       'Ended'
        TERMINATED = 'TERMINATED',  'Terminated'

    class BillingDay(models.IntegerChoices):
        FIRST = 1,  '1st of month'
        FIFTH = 5,  '5th of month'
        TENTH = 10, '10th of month'
        FIFTEENTH = 15, '15th of month'

    # ── Identity ──────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.PROTECT,
        related_name='tenancies'
    )

    # ── Core Relationships ────────────────────────────────
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.PROTECT,
        related_name='tenancies'
    )
    unit = models.ForeignKey(
        'properties.Unit',
        on_delete=models.PROTECT,
        related_name='tenancies'
    )

    # ── Dates ─────────────────────────────────────────────
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    # ── Financials ────────────────────────────────────────
    monthly_rent = models.DecimalField(max_digits=10, decimal_places=2)
    required_deposit = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    billing_day = models.IntegerField(
        choices=BillingDay.choices,
        default=BillingDay.FIRST
    )

    # ── Status ────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    termination_reason = models.TextField(blank=True)

    # ── Migration flag ────────────────────────────────────
    is_opening_balance = models.BooleanField(
        default=False,
        help_text='True if this tenancy was created during migration'
    )

    # ── Timestamps ────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='tenancies_created',
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = 'Tenancy'
        verbose_name_plural = 'Tenancies'
        ordering = ['-start_date']

    def __str__(self):
        return f'{self.tenant.full_name} — {self.unit} ({self.status})'

    def clean(self):
        """
        Enforce: only one ACTIVE tenancy per unit at a time.
        """
        if self.status == self.Status.ACTIVE and self.unit_id:
            conflict = Tenancy.objects.filter(
                unit_id=self.unit_id,
                status=self.Status.ACTIVE
            ).exclude(pk=self.pk)

            if conflict.exists():
                raise ValidationError(
                    f'Unit {self.unit.unit_number} already has an active tenancy. '
                    f'End the existing tenancy before creating a new one.'
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def get_duration_months(self):
        """Returns number of months the tenancy has been active."""
        end = self.end_date or timezone.now().date()
        delta = end - self.start_date
        return max(1, round(delta.days / 30))

    def is_active(self):
        return self.status == self.Status.ACTIVE

    def get_status_badge(self):
        badge_map = {
            self.Status.ACTIVE:      'rw-badge-success',
            self.Status.TRANSFERRED: 'rw-badge-info',
            self.Status.ENDED:       'rw-badge-dark',
            self.Status.TERMINATED:  'rw-badge-danger',
        }
        return badge_map.get(self.status, 'rw-badge-dark')


class RentVariation(models.Model):
    """
    Records every rent increase or decrease with effective date.
    Preserves full rent history — never silently overwrites monthly_rent.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenancy = models.ForeignKey(
        Tenancy,
        on_delete=models.PROTECT,
        related_name='rent_variations'
    )
    previous_rent = models.DecimalField(max_digits=10, decimal_places=2)
    new_rent = models.DecimalField(max_digits=10, decimal_places=2)
    effective_date = models.DateField()
    reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='rent_variations_approved',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='rent_variations_created',
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = 'Rent Variation'
        verbose_name_plural = 'Rent Variations'
        ordering = ['-effective_date']

    def __str__(self):
        return (
            f'{self.tenancy.tenant.full_name} — '
            f'KSh {self.previous_rent} → KSh {self.new_rent} '
            f'(effective {self.effective_date})'
        )
