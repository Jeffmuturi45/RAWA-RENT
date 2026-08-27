import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone


# ──────────────────────────────────────────────────────────────
# CHARGE
# ──────────────────────────────────────────────────────────────

class Charge(models.Model):
    """
    An obligation owed by a tenancy (the debit side of the ledger).
    Balances are always derived from allocations — never stored.
    """

    class Type(models.TextChoices):
        RENT = 'RENT',            'Rent'
        DEPOSIT = 'DEPOSIT',         'Deposit'
        UTILITY = 'UTILITY',         'Utility'
        LATE_FEE = 'LATE_FEE',        'Late Fee'
        OTHER = 'OTHER',           'Other'
        OPENING_ARREARS = 'OPENING_ARREARS', 'Opening Arrears'

    class Status(models.TextChoices):
        UNPAID = 'UNPAID',  'Unpaid'
        PARTIAL = 'PARTIAL', 'Partially Paid'
        PAID = 'PAID',    'Paid'
        OVERDUE = 'OVERDUE', 'Overdue'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.PROTECT,
        related_name='charges')
    tenancy = models.ForeignKey(
        'tenancies.Tenancy', on_delete=models.PROTECT, related_name='charges')

    charge_type = models.CharField(max_length=20, choices=Type.choices)
    description = models.CharField(max_length=255, blank=True)

    # Rent charges cover a period; other charge types leave these null.
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()

    # Deposit charges: mark so we never generate a second one for same tenancy
    is_deposit_charge = models.BooleanField(default=False)
    is_opening_balance = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='charges_created', null=True, blank=True)

    class Meta:
        verbose_name = 'Charge'
        verbose_name_plural = 'Charges'
        ordering = ['due_date', 'created_at']
        constraints = [
            # One rent charge per tenancy per period → idempotent generation.
            models.UniqueConstraint(
                fields=['tenancy', 'charge_type', 'period_start'],
                name='uniq_charge_tenancy_type_period',
            ),
            models.CheckConstraint(
                check=models.Q(amount__gte=0),
                name='charge_amount_non_negative',
            ),
        ]
        indexes = [
            models.Index(fields=['tenancy', 'due_date']),
        ]

    def __str__(self):
        return f'{self.get_charge_type_display()} — KSh {self.amount} ({self.due_date})'

    @property
    def amount_allocated(self):
        agg = self.allocations.aggregate(t=models.Sum('amount'))['t']
        return agg or Decimal('0')

    @property
    def balance(self):
        return self.amount - self.amount_allocated

    @property
    def status(self):
        allocated = self.amount_allocated
        if allocated >= self.amount and self.amount > 0:
            return self.Status.PAID
        if allocated > 0:
            return self.Status.PARTIAL
        if self.due_date and self.due_date < timezone.now().date():
            return self.Status.OVERDUE
        return self.Status.UNPAID

    def get_status_badge(self):
        return {
            self.Status.PAID:    'rw-badge-success',
            self.Status.PARTIAL: 'rw-badge-info',
            self.Status.UNPAID:  'rw-badge-warning',
            self.Status.OVERDUE: 'rw-badge-danger',
        }.get(self.status, 'rw-badge-dark')


# ──────────────────────────────────────────────────────────────
# PAYMENT
# ──────────────────────────────────────────────────────────────

class Payment(models.Model):
    """Money received from a tenant (the credit side)."""

    class Method(models.TextChoices):
        MPESA = 'MPESA',  'M-Pesa'
        BANK = 'BANK',   'Bank Transfer'
        CASH = 'CASH',   'Cash'
        CHEQUE = 'CHEQUE', 'Cheque'
        OTHER = 'OTHER',  'Other'

    class Status(models.TextChoices):
        PENDING_VERIFICATION = 'PENDING_VERIFICATION', 'Pending Verification'
        VERIFIED = 'VERIFIED',             'Verified'
        REJECTED = 'REJECTED',             'Rejected'
        REVERSED = 'REVERSED',             'Reversed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.PROTECT,
        related_name='payments')
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.PROTECT, related_name='payments')
    tenancy = models.ForeignKey(
        'tenancies.Tenancy', on_delete=models.PROTECT,
        related_name='payments', null=True, blank=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField()
    method = models.CharField(max_length=10, choices=Method.choices)

    # M-Pesa / bank transaction code. NULL when blank so many cash payments
    # are allowed, but any non-null code is globally unique (dup protection).
    reference = models.CharField(
        max_length=64, null=True, blank=True, unique=True)

    status = models.CharField(
        max_length=25, choices=Status.choices,
        default=Status.PENDING_VERIFICATION)   # ← portal uploads start PENDING
    notes = models.TextField(blank=True)

    # Proof of payment uploaded by tenant via portal
    proof_of_payment = models.FileField(
        upload_to='payment_proofs/', null=True, blank=True)

    # ── Verification ───────────────────────────────────────
    verified_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='payments_verified', null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='payments_created', null=True, blank=True)

    class Meta:
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-payment_date', '-created_at']
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='payment_amount_positive',
            ),
        ]
        indexes = [
            models.Index(fields=['organization', '-payment_date']),
            models.Index(fields=['tenant']),
        ]

    def __str__(self):
        return f'{self.tenant.full_name} — KSh {self.amount} ({self.get_method_display()})'

    @property
    def charge_allocated(self):
        agg = self.allocations.aggregate(t=models.Sum('amount'))['t']
        return agg or Decimal('0')

    @property
    def deposit_allocated(self):
        agg = self.deposit_movements.aggregate(t=models.Sum('amount'))['t']
        return agg or Decimal('0')

    @property
    def total_allocated(self):
        return self.charge_allocated + self.deposit_allocated

    @property
    def unallocated(self):
        return self.amount - self.total_allocated

    def get_status_badge(self):
        return {
            self.Status.VERIFIED:             'rw-badge-success',
            self.Status.PENDING_VERIFICATION: 'rw-badge-warning',
            self.Status.REJECTED:             'rw-badge-danger',
            self.Status.REVERSED:             'rw-badge-dark',
        }.get(self.status, 'rw-badge-dark')


# ──────────────────────────────────────────────────────────────
# PAYMENT ALLOCATION
# ──────────────────────────────────────────────────────────────

class PaymentAllocation(models.Model):
    """Explains how much of a Payment settled a specific Charge."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, related_name='allocations')
    charge = models.ForeignKey(
        Charge, on_delete=models.PROTECT, related_name='allocations')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Payment Allocation'
        verbose_name_plural = 'Payment Allocations'
        ordering = ['created_at']
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='allocation_amount_positive',
            ),
        ]

    def __str__(self):
        return f'KSh {self.amount} → {self.charge}'


# ──────────────────────────────────────────────────────────────
# DEPOSIT ACCOUNT + MOVEMENTS
# ──────────────────────────────────────────────────────────────

class DepositAccount(models.Model):
    """A tenancy's deposit ledger. Balance derived from movements."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.PROTECT,
        related_name='deposit_accounts')
    tenancy = models.OneToOneField(
        'tenancies.Tenancy', on_delete=models.PROTECT,
        related_name='deposit_account')
    required_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Deposit Account'
        verbose_name_plural = 'Deposit Accounts'

    def __str__(self):
        return f'Deposit — {self.tenancy}'

    @property
    def balance(self):
        agg = self.movements.aggregate(t=models.Sum('amount'))['t']
        return agg or Decimal('0')

    @property
    def shortfall(self):
        return max(Decimal('0'), self.required_amount - self.balance)

    @property
    def is_fully_paid(self):
        return self.balance >= self.required_amount


class DepositMovement(models.Model):
    """
    A single deposit ledger entry.
    amount is signed: positive = into deposit, negative = out.
    """

    class Type(models.TextChoices):
        RECEIVED = 'RECEIVED',     'Received'
        OPENING = 'OPENING',      'Opening Balance'
        DEDUCTION = 'DEDUCTION',    'Deduction'
        REFUND = 'REFUND',       'Refund'
        TRANSFER_IN = 'TRANSFER_IN',  'Transfer In'
        TRANSFER_OUT = 'TRANSFER_OUT', 'Transfer Out'
        TOPUP = 'TOPUP',        'Top-up (unit transfer)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    deposit_account = models.ForeignKey(
        DepositAccount, on_delete=models.PROTECT, related_name='movements')
    movement_type = models.CharField(max_length=15, choices=Type.choices)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text='Signed: positive increases deposit, negative decreases it.')
    reason = models.CharField(max_length=255, blank=True)
    related_payment = models.ForeignKey(
        Payment, on_delete=models.SET_NULL, related_name='deposit_movements',
        null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='deposit_movements_created', null=True, blank=True)

    class Meta:
        verbose_name = 'Deposit Movement'
        verbose_name_plural = 'Deposit Movements'
        ordering = ['created_at']
        constraints = [
            models.CheckConstraint(
                check=~models.Q(amount=0),
                name='deposit_movement_nonzero',
            ),
        ]

    def __str__(self):
        return f'{self.get_movement_type_display()} KSh {self.amount}'


# ──────────────────────────────────────────────────────────────
# ADJUSTMENT
# ──────────────────────────────────────────────────────────────

class Adjustment(models.Model):
    """Manual correction to a tenancy account (with mandatory reason + audit)."""

    class Direction(models.TextChoices):
        DEBIT = 'DEBIT',  'Debit (increase what tenant owes)'
        CREDIT = 'CREDIT', 'Credit (reduce what tenant owes)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.PROTECT,
        related_name='adjustments')
    tenancy = models.ForeignKey(
        'tenancies.Tenancy', on_delete=models.PROTECT,
        related_name='adjustments')
    direction = models.CharField(max_length=6, choices=Direction.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    effective_date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='adjustments_created', null=True, blank=True)
    approved_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='adjustments_approved', null=True, blank=True)

    class Meta:
        verbose_name = 'Adjustment'
        verbose_name_plural = 'Adjustments'
        ordering = ['-effective_date', '-created_at']
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='adjustment_amount_positive',
            ),
        ]

    def __str__(self):
        return f'{self.get_direction_display()} KSh {self.amount} — {self.tenancy}'

    @property
    def signed_amount(self):
        """Positive = increases what the tenant owes."""
        return self.amount if self.direction == self.Direction.DEBIT else -self.amount


# ──────────────────────────────────────────────────────────────
# RENT NOTICE  (tenant portal — proof of payment workflow)
# ──────────────────────────────────────────────────────────────

class RentNotice(models.Model):
    """
    Generated monthly per tenancy. Tenant uploads proof, agency approves.
    Once approved, the notice is hidden from the tenant portal and the
    underlying Charge is marked PAID via PaymentAllocation.
    """

    class Status(models.TextChoices):
        PENDING = 'PENDING',   'Pending Payment'
        SUBMITTED = 'SUBMITTED', 'Proof Submitted'
        APPROVED = 'APPROVED',  'Approved'
        REJECTED = 'REJECTED',  'Rejected — Resubmit'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.PROTECT,
        related_name='rent_notices')
    tenancy = models.ForeignKey(
        'tenancies.Tenancy', on_delete=models.PROTECT,
        related_name='rent_notices')

    # Link to the underlying Charge so approval can auto-allocate
    charge = models.OneToOneField(
        Charge, on_delete=models.PROTECT,
        related_name='rent_notice', null=True, blank=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    period_start = models.DateField()
    period_end = models.DateField()
    due_date = models.DateField()

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING)

    # Tenant uploads this
    proof_of_payment = models.FileField(
        upload_to='rent_proofs/%Y/%m/', null=True, blank=True)
    proof_uploaded_at = models.DateTimeField(null=True, blank=True)

    # Agency fills these on approval
    approved_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        related_name='rent_notices_approved', null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        related_name='rent_notices_created', null=True, blank=True)

    class Meta:
        verbose_name = 'Rent Notice'
        verbose_name_plural = 'Rent Notices'
        ordering = ['-period_start']
        # One notice per tenancy per period — idempotent generation
        constraints = [
            models.UniqueConstraint(
                fields=['tenancy', 'period_start'],
                name='uniq_rent_notice_tenancy_period',
            ),
        ]

    def __str__(self):
        return (
            f'Rent Notice — {self.tenancy.tenant.full_name} '
            f'({self.period_start} → {self.period_end})'
        )

    @property
    def is_overdue(self):
        return (
            self.status in (self.Status.PENDING, self.Status.REJECTED)
            and self.due_date < timezone.now().date()
        )

    def get_status_badge(self):
        return {
            self.Status.PENDING:   'rw-badge-warning',
            self.Status.SUBMITTED: 'rw-badge-info',
            self.Status.APPROVED:  'rw-badge-success',
            self.Status.REJECTED:  'rw-badge-danger',
        }.get(self.status, 'rw-badge-dark')


# MaintenanceRequest, MoveOutRequest, TransferRequest live in portal/models.py
