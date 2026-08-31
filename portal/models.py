import uuid
from django.core.checks import messages
from django.db import models, transaction
from django.utils import timezone
from django.db.models import Q
from requests import request

# ──────────────────────────────────────────────────────────────
# MAINTENANCE REQUEST
# ──────────────────────────────────────────────────────────────


class MaintenanceRequest(models.Model):

    class Status(models.TextChoices):
        PENDING = 'PENDING',     'Pending'
        ASSIGNED = 'ASSIGNED',    'Assigned'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        RESOLVED = 'RESOLVED',    'Resolved'
        REJECTED = 'REJECTED',    'Rejected'
        CLOSED = 'CLOSED',      'Closed'

    class Priority(models.TextChoices):
        LOW = 'LOW',    'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH',   'High'
        URGENT = 'URGENT', 'Urgent'

    class Category(models.TextChoices):
        PLUMBING = 'PLUMBING',   'Plumbing'
        ELECTRICAL = 'ELECTRICAL', 'Electrical'
        STRUCTURAL = 'STRUCTURAL', 'Structural / Walls'
        APPLIANCES = 'APPLIANCES', 'Appliances'
        PEST = 'PEST',       'Pest Control'
        CLEANING = 'CLEANING',   'Cleaning'
        OTHER = 'OTHER',      'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.PROTECT,
        related_name='maintenance_requests')
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.PROTECT,
        related_name='maintenance_requests')
    tenancy = models.ForeignKey(
        'tenancies.Tenancy', on_delete=models.PROTECT,
        related_name='maintenance_requests')

    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.OTHER)
    title = models.CharField(max_length=255)
    description = models.TextField()
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING)

    # Tenant attaches a photo
    photo = models.ImageField(
        upload_to='maintenance_photos/%Y/%m/', null=True, blank=True)

    # Agency assigns technician
    assigned_to = models.CharField(max_length=255, blank=True,
                                   help_text='Technician or staff name')
    assigned_at = models.DateTimeField(null=True, blank=True)
    staff_notes = models.TextField(blank=True)

    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='maintenance_requests_resolved', null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    # Tenant rates after resolution (1–5)
    tenant_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    tenant_feedback = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.tenant.full_name} — {self.title} ({self.status})'

    def mark_resolved(self, user=None, notes=''):
        self.status = self.Status.RESOLVED
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.resolution_notes = notes
        self.save(update_fields=[
            'status', 'resolved_at', 'resolved_by',
            'resolution_notes', 'updated_at',
        ])

    def get_status_badge(self):
        return {
            self.Status.PENDING:     'rw-badge-warning',
            self.Status.ASSIGNED:    'rw-badge-info',
            self.Status.IN_PROGRESS: 'rw-badge-info',
            self.Status.RESOLVED:    'rw-badge-success',
            self.Status.REJECTED:    'rw-badge-danger',
            self.Status.CLOSED:      'rw-badge-dark',
        }.get(self.status, 'rw-badge-dark')

    def get_priority_badge(self):
        return {
            self.Priority.LOW:    'rw-badge-success',
            self.Priority.MEDIUM: 'rw-badge-warning',
            self.Priority.HIGH:   'rw-badge-danger',
            self.Priority.URGENT: 'rw-badge-danger',
        }.get(self.priority, 'rw-badge-dark')


# ──────────────────────────────────────────────────────────────
# TRANSFER REQUEST
# ──────────────────────────────────────────────────────────────

class TransferRequest(models.Model):

    class Status(models.TextChoices):
        PENDING = 'PENDING',   'Pending'
        APPROVED = 'APPROVED',  'Approved'
        REJECTED = 'REJECTED',  'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled'
        COMPLETED = 'COMPLETED', 'Completed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.PROTECT,
        related_name='transfer_requests'
    )
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.PROTECT,
        related_name='transfer_requests'
    )
    tenancy = models.ForeignKey(
        'tenancies.Tenancy', on_delete=models.PROTECT,
        related_name='transfer_requests'
    )
    requested_unit = models.ForeignKey(
        'properties.Unit', on_delete=models.PROTECT,
        related_name='transfer_requests'
    )

    # Effective = end of current month; tenant starts new unit 1st of next month
    requested_date = models.DateField()
    effective_date = models.DateField(
        null=True, blank=True,
        help_text='Last day of current month — new tenancy starts 1st of next month'
    )
    reason = models.TextField()

    # Deposit carry-over (calculated when request is created)
    old_deposit = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    new_deposit = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    deposit_difference = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Positive = tenant must top up. Negative = credit/refund.'
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    staff_notes = models.TextField(blank=True)

    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='transfer_requests_reviewed', null=True, blank=True
    )
    rejection_note = models.TextField(blank=True)

    # Track when the transfer was actually completed (for cooldown)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Optional: track if this was admin-approved to bypass cooldown
    bypassed_cooldown = models.BooleanField(default=False)
    bypassed_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='transfer_requests_bypassed', null=True, blank=True
    )
    bypassed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        # For PostgreSQL - supports conditional unique constraint
        # For MySQL, this constraint will be ignored/skipped during migration
        # constraints = [
        #     models.UniqueConstraint(
        #         fields=['tenancy'],
        #         condition=Q(status='PENDING'),
        #         name='one_pending_transfer_per_tenancy'
        #     )
        # ]

    def __str__(self):
        return (
            f'{self.tenant.full_name} — '
            f'{self.tenancy.unit.unit_number} → '
            f'{self.requested_unit.unit_number}'
        )

    def can_transfer(self):
        """Check if this tenant can request another transfer."""
        if self.status in [self.Status.PENDING, self.Status.APPROVED]:
            return False

        # If completed, check cooldown
        if self.status == self.Status.COMPLETED:
            completed_date = self.completed_at or self.updated_at
            if completed_date:
                days_since = (timezone.now() - completed_date).days
                return days_since >= 30

        # Rejected/Cancelled requests don't block new requests
        return True

    def days_remaining_for_transfer(self):
        """Return days remaining in cooldown period, or 0 if eligible."""
        if self.status != self.Status.COMPLETED:
            return 0

        completed_date = self.completed_at or self.updated_at
        if not completed_date:
            return 0

        days_since = (timezone.now() - completed_date).days
        if days_since >= 30:
            return 0

        return 30 - days_since

    def get_status_badge(self):
        return {
            self.Status.PENDING:   'rw-badge-warning',
            self.Status.APPROVED:  'rw-badge-success',
            self.Status.REJECTED:  'rw-badge-danger',
            self.Status.CANCELLED: 'rw-badge-dark',
            self.Status.COMPLETED: 'rw-badge-info',
        }.get(self.status, 'rw-badge-dark')

# ──────────────────────────────────────────────────────────────
# MOVE-OUT REQUEST
# ──────────────────────────────────────────────────────────────


class MoveOutRequest(models.Model):
    """
    Tenant-initiated move-out request.
    Agency sends inspector who ticks the checklist step by step.
    Tenant sees live progress on the portal.
    On approval the tenancy is ended and deposit settlement is calculated.
    """

    class Status(models.TextChoices):
        PENDING = 'PENDING',    'Pending Review'
        INSPECTION = 'INSPECTION', 'Under Inspection'
        APPROVED = 'APPROVED',   'Approved'
        REJECTED = 'REJECTED',   'Rejected'
        CANCELLED = 'CANCELLED',  'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.PROTECT,
        related_name='moveout_requests')
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.PROTECT,
        related_name='moveout_requests')
    tenancy = models.ForeignKey(
        'tenancies.Tenancy', on_delete=models.PROTECT,
        related_name='moveout_requests')

    requested_moveout_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING)

    # ── Inspection checklist ──────────────────────────────
    # None = not yet inspected | True = OK | False = issue found
    insp_walls = models.BooleanField(null=True, blank=True)
    insp_plumbing = models.BooleanField(null=True, blank=True)
    insp_electrical = models.BooleanField(null=True, blank=True)
    insp_windows = models.BooleanField(null=True, blank=True)
    insp_flooring = models.BooleanField(null=True, blank=True)
    insp_cleanliness = models.BooleanField(null=True, blank=True)
    insp_keys = models.BooleanField(null=True, blank=True)
    insp_notes = models.TextField(blank=True)

    inspected_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        related_name='moveout_inspections', null=True, blank=True)
    inspected_at = models.DateTimeField(null=True, blank=True)

    # ── Deposit settlement (filled on approval) ───────────
    deposit_held = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)
    outstanding_arrears = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Total unpaid charges from day 1 of tenancy')
    damage_deductions = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)
    deposit_refundable = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='deposit_held - outstanding_arrears - damage_deductions')

    # ── Agency decision ───────────────────────────────────
    staff_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='moveout_requests_reviewed', null=True, blank=True)
    rejection_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.tenant.full_name} — Move-out {self.requested_moveout_date}'

    # ── Checklist helpers ─────────────────────────────────

    CHECKLIST_FIELDS = [
        ('insp_walls',       'Walls & Paintwork'),
        ('insp_plumbing',    'Plumbing & Water'),
        ('insp_electrical',  'Electrical & Switches'),
        ('insp_windows',     'Windows & Doors'),
        ('insp_flooring',    'Flooring & Tiles'),
        ('insp_cleanliness', 'General Cleanliness'),
        ('insp_keys',        'Keys Returned'),
    ]

    @property
    def checklist_items(self):
        """Returns list of dicts ready for template rendering."""
        result = []
        for field, label in self.CHECKLIST_FIELDS:
            value = getattr(self, field)
            if value is True:
                status = 'ok'
            elif value is False:
                status = 'issue'
            else:
                status = 'pending'
            result.append({'field': field, 'label': label, 'status': status})
        return result

    @property
    def checklist_complete(self):
        return all(
            getattr(self, f) is not None
            for f, _ in self.CHECKLIST_FIELDS
        )

    @property
    def checklist_progress(self):
        """Returns (checked_count, total_count)."""
        checked = sum(
            1 for f, _ in self.CHECKLIST_FIELDS
            if getattr(self, f) is not None
        )
        return checked, len(self.CHECKLIST_FIELDS)

    @property
    def has_issues(self):
        return any(
            getattr(self, f) is False
            for f, _ in self.CHECKLIST_FIELDS
        )

    def calculate_deposit_refund(self):
        """
        Calculates deposit_refundable from held deposit,
        outstanding arrears (all unpaid charges since tenancy start),
        and damage deductions.
        Called by the admin approval view.
        """
        from finance.models import Charge
        from decimal import Decimal

        # Sum all unpaid charge balances for this tenancy
        charges = Charge.objects.filter(tenancy=self.tenancy)
        total_arrears = Decimal('0')
        for charge in charges:
            bal = charge.balance
            if bal > 0:
                total_arrears += bal

        try:
            deposit_held = self.tenancy.deposit_account.balance
        except Exception:
            deposit_held = Decimal('0')

        refundable = max(
            Decimal('0'),
            deposit_held - total_arrears - self.damage_deductions
        )

        self.deposit_held = deposit_held
        self.outstanding_arrears = total_arrears
        self.deposit_refundable = refundable
        self.save(update_fields=[
            'deposit_held', 'outstanding_arrears', 'deposit_refundable'
        ])
        return refundable

    def get_status_badge(self):
        return {
            self.Status.PENDING:    'rw-badge-warning',
            self.Status.INSPECTION: 'rw-badge-info',
            self.Status.APPROVED:   'rw-badge-success',
            self.Status.REJECTED:   'rw-badge-danger',
            self.Status.CANCELLED:  'rw-badge-dark',
        }.get(self.status, 'rw-badge-dark')

    def get_status_step(self):
        """Returns 1-4 for the progress stepper on the portal."""
        return {
            self.Status.PENDING:    1,
            self.Status.INSPECTION: 2,
            self.Status.APPROVED:   4,
            self.Status.REJECTED:   4,
            self.Status.CANCELLED:  4,
        }.get(self.status, 1)
