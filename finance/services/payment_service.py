"""
Payment lifecycle — claim → verify → (allocate) — atomic and audit-logged.

Spec §19/§20/§28: a payment must never become VERIFIED merely because
someone typed a transaction code. Staff record a *claim*; a different
authorised user verifies it against the real M-Pesa statement, using their
financial PIN. Only VERIFIED payments touch the ledger.
"""
from decimal import Decimal

from django.contrib.auth.hashers import check_password
from django.db import transaction, IntegrityError
from django.utils import timezone

from audit.services import log_action, Action
from ..models import Payment, DepositMovement
from . import allocation_service, deposit_service


class DuplicatePaymentError(Exception):
    """Raised when a payment reference (M-Pesa code) already exists."""


class SelfVerificationError(Exception):
    """Raised when the user who recorded a claim tries to verify it (§28)."""


class InvalidPinError(Exception):
    """Raised when the verifier's financial PIN is missing or wrong."""


class InvalidStateError(Exception):
    """Raised when a payment is not in a state that allows the operation."""


def _assert_reference_unique(reference):
    if reference and Payment.objects.filter(reference=reference).exists():
        raise DuplicatePaymentError(
            'This M-Pesa transaction has already been recorded.')


def _create_payment(*, organization, tenant, tenancy, amount, payment_date,
                    method, reference, status, notes, actor):
    try:
        return Payment.objects.create(
            organization=organization,
            tenant=tenant,
            tenancy=tenancy,
            amount=amount,
            payment_date=payment_date,
            method=method,
            reference=reference or None,
            status=status,
            notes=notes,
            created_by=actor,
        )
    except IntegrityError:
        # Lost a race on the unique reference constraint.
        raise DuplicatePaymentError(
            'This M-Pesa transaction has already been recorded.')


def _apply_to_ledger(payment, *, deposit_amount=0, allocations=None,
                     actor=None, ip=''):
    """
    Move money into the ledger: deposit portion first (kept separate from
    rent), then allocate the remainder across outstanding charges.
    Called only once a payment is VERIFIED.
    """
    deposit_amount = Decimal(deposit_amount or 0)
    tenancy = payment.tenancy

    if deposit_amount > 0 and tenancy is not None:
        deposit_service.record_movement(
            tenancy, DepositMovement.Type.RECEIVED, deposit_amount,
            reason=f'From payment {payment.reference or payment.pk}',
            related_payment=payment, actor=actor, ip=ip,
        )

    if tenancy is not None:
        if allocations:
            allocation_service.manual_allocate(payment, allocations)
        else:
            allocation_service.auto_allocate(payment)


# ─────────────────────────────────────────
# STEP 1 — CLAIM
# ─────────────────────────────────────────
@transaction.atomic
def record_payment_claim(*, organization, tenant, amount, payment_date, method,
                         reference='', tenancy=None, deposit_amount=0,
                         notes='', actor=None, ip=''):
    """
    Record a payment CLAIM (PENDING_VERIFICATION). Nothing is allocated and
    arrears are unaffected until someone verifies it.

    The intended deposit split is remembered in `notes` metadata via the
    caller; allocation happens at verification time.
    """
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError('Payment amount must be positive.')

    deposit_amount = Decimal(deposit_amount or 0)
    if deposit_amount < 0 or deposit_amount > amount:
        raise ValueError('Deposit portion is invalid.')

    reference = (reference or '').strip()
    if tenancy is None:
        tenancy = tenant.get_active_tenancy()

    _assert_reference_unique(reference)

    payment = _create_payment(
        organization=organization, tenant=tenant, tenancy=tenancy,
        amount=amount, payment_date=payment_date, method=method,
        reference=reference, status=Payment.Status.PENDING_VERIFICATION,
        notes=notes, actor=actor,
    )

    log_action(
        Action.PAYMENT_CLAIM_CREATED, actor=actor, organization=organization,
        obj=payment,
        after={'amount': str(amount), 'method': method,
               'reference': reference or '', 'status': payment.status},
        ip=ip,
    )
    return payment


# ─────────────────────────────────────────
# STEP 2 — VERIFY / REJECT
# ─────────────────────────────────────────
@transaction.atomic
def verify_payment(payment, *, actor, pin, deposit_amount=0,
                   allocations=None, ip=''):
    """
    Verify a pending claim and post it to the ledger.

    Enforces (§28):
      - the payment must be PENDING_VERIFICATION
      - the verifier must NOT be the user who recorded the claim
      - the verifier must supply their correct financial PIN
    """
    payment = Payment.objects.select_for_update().get(pk=payment.pk)

    if payment.status != Payment.Status.PENDING_VERIFICATION:
        raise InvalidStateError(
            f'Only pending payments can be verified '
            f'(this one is {payment.get_status_display()}).')

    if payment.created_by_id and actor is not None \
            and payment.created_by_id == actor.pk:
        raise SelfVerificationError(
            'You recorded this payment, so you cannot verify it. '
            'Another authorised user must verify it.')

    if actor is None or not actor.financial_pin:
        raise InvalidPinError(
            'You must set a financial PIN on your profile before verifying payments.')
    if not pin or not check_password(pin, actor.financial_pin):
        raise InvalidPinError('Incorrect financial PIN.')

    payment.status = Payment.Status.VERIFIED
    payment.verified_by = actor
    payment.verified_at = timezone.now()
    payment.save(update_fields=['status', 'verified_by', 'verified_at'])

    _apply_to_ledger(payment, deposit_amount=deposit_amount,
                     allocations=allocations, actor=actor, ip=ip)

    log_action(
        Action.PAYMENT_VERIFIED, actor=actor, organization=payment.organization,
        obj=payment,
        before={'status': Payment.Status.PENDING_VERIFICATION},
        after={'status': payment.status,
               'allocated': str(payment.total_allocated),
               'unallocated': str(payment.unallocated),
               'claimed_by': str(payment.created_by_id or '')},
        ip=ip,
    )
    return payment


@transaction.atomic
def reject_payment(payment, *, actor, reason, ip=''):
    """Reject a pending claim. Nothing is posted to the ledger."""
    payment = Payment.objects.select_for_update().get(pk=payment.pk)

    if payment.status != Payment.Status.PENDING_VERIFICATION:
        raise InvalidStateError('Only pending payments can be rejected.')
    if not (reason or '').strip():
        raise ValueError('A rejection reason is required.')

    payment.status = Payment.Status.REJECTED
    payment.rejection_reason = reason
    payment.save(update_fields=['status', 'rejection_reason'])

    log_action(
        Action.PAYMENT_REJECTED, actor=actor, organization=payment.organization,
        obj=payment,
        before={'status': Payment.Status.PENDING_VERIFICATION},
        after={'status': payment.status},
        reason=reason, ip=ip,
    )
    return payment


# ─────────────────────────────────────────
# DIRECT RECORD — migration / opening balances only
# ─────────────────────────────────────────
@transaction.atomic
def record_payment(*, organization, tenant, amount, payment_date, method,
                   reference='', tenancy=None, allocations=None,
                   deposit_amount=0, notes='', actor=None, ip=''):
    """
    Create an already-VERIFIED payment and post it immediately.

    NOT for day-to-day staff entry — use record_payment_claim() +
    verify_payment() so segregation of duties (§28) is preserved. This exists
    for data migration and opening balances, where the money is historical and
    has already been reconciled outside the system.
    """
    amount = Decimal(amount)
    deposit_amount = Decimal(deposit_amount or 0)

    if amount <= 0:
        raise ValueError('Payment amount must be positive.')
    if deposit_amount < 0 or deposit_amount > amount:
        raise ValueError('Deposit portion is invalid.')

    reference = (reference or '').strip()
    if tenancy is None:
        tenancy = tenant.get_active_tenancy()

    _assert_reference_unique(reference)

    payment = _create_payment(
        organization=organization, tenant=tenant, tenancy=tenancy,
        amount=amount, payment_date=payment_date, method=method,
        reference=reference, status=Payment.Status.VERIFIED,
        notes=notes, actor=actor,
    )

    _apply_to_ledger(payment, deposit_amount=deposit_amount,
                     allocations=allocations, actor=actor, ip=ip)

    log_action(
        Action.PAYMENT_RECORDED, actor=actor, organization=organization,
        obj=payment,
        after={
            'amount': str(amount), 'method': method,
            'reference': reference or '', 'deposit': str(deposit_amount),
            'allocated': str(payment.total_allocated),
            'unallocated': str(payment.unallocated),
        },
        ip=ip,
    )
    return payment
