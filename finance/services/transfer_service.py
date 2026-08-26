"""
Tenant transfer service.

Handles the full atomic workflow of moving a tenant from one unit to another:
  1. Validates both tenancies
  2. Calculates financial position
  3. Closes old tenancy
  4. Transfers deposit
  5. Creates new tenancy
  6. Handles deposit difference (top-up charge OR surplus disposition)
  7. Carries outstanding rent to new tenancy
  8. Creates Transfer record
  9. Updates unit statuses
  10. Audit logs everything
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from audit.services import log_action, Action
from finance.models import Charge, DepositMovement
from finance.services import deposit_service
from tenancies.models import Tenancy, Transfer


class TransferError(Exception):
    """Raised when a transfer cannot proceed."""


def calculate_transfer_summary(old_tenancy, new_unit):
    """
    Returns a dict summarising the financial impact of a transfer.
    Call this BEFORE confirming — show it to the manager for review.
    """
    from finance.models import DepositAccount
    from finance.services.arrears_service import outstanding_total

    # Deposit held on old tenancy
    try:
        old_deposit_held = old_tenancy.deposit_account.balance
    except DepositAccount.DoesNotExist:
        old_deposit_held = Decimal('0')

    new_deposit_required = new_unit.deposit_amount
    deposit_difference = new_deposit_required - old_deposit_held
    # Positive = tenant owes top-up
    # Negative = surplus in tenant's favour

    # Outstanding rent on old tenancy
    outstanding_charges = [
        c for c in Charge.objects.filter(tenancy=old_tenancy)
        if c.balance > 0
    ]
    outstanding_rent = sum(
        (c.balance for c in outstanding_charges), Decimal('0')
    )

    return {
        'old_unit':              old_tenancy.unit,
        'new_unit':              new_unit,
        'old_monthly_rent':      old_tenancy.monthly_rent,
        'new_monthly_rent':      new_unit.rent_amount,
        'old_deposit_held':      old_deposit_held,
        'new_deposit_required':  new_deposit_required,
        'deposit_difference':    deposit_difference,
        'outstanding_rent':      outstanding_rent,
        'outstanding_charges':   outstanding_charges,
        'has_topup':             deposit_difference > 0,
        'has_surplus':           deposit_difference < 0,
        'surplus_amount':        abs(deposit_difference) if deposit_difference < 0 else Decimal('0'),
        'topup_amount':          deposit_difference if deposit_difference > 0 else Decimal('0'),
    }


@transaction.atomic
def execute_transfer(
    *,
    old_tenancy,
    new_unit,
    transfer_date,
    new_monthly_rent=None,
    new_required_deposit=None,
    deposit_disposition,
    reason='',
    notes='',
    actor=None,
    ip='',
):
    """
    Executes the full transfer workflow atomically.

    deposit_disposition choices:
      'TOPUP'       — tenant will pay a top-up (creates deposit charge)
      'REFUND'      — surplus refunded to tenant (deposit movement REFUND)
      'RENT_CREDIT' — surplus credited against next rent charge
      'HOLD'        — surplus stays in deposit as overpayment
      'EXACT'       — no difference

    Returns the Transfer record.
    """
    from properties.models import Unit

    # ── Validation ────────────────────────────────────────
    if old_tenancy.status != Tenancy.Status.ACTIVE:
        raise TransferError('Only active tenancies can be transferred.')

    if new_unit.status == Unit.Status.OCCUPIED:
        raise TransferError(
            f'Unit {new_unit.unit_number} is already occupied.'
        )

    if new_unit.pk == old_tenancy.unit.pk:
        raise TransferError(
            'New unit must be different from the current unit.')

    if new_unit.prop.organization != old_tenancy.organization:
        raise TransferError('New unit belongs to a different organization.')

    # ── Financial snapshot ────────────────────────────────
    summary = calculate_transfer_summary(old_tenancy, new_unit)

    new_monthly_rent = new_monthly_rent or new_unit.rent_amount
    new_required_deposit = new_required_deposit or new_unit.deposit_amount
    old_deposit_held = summary['old_deposit_held']
    deposit_difference = summary['deposit_difference']
    outstanding_rent = summary['outstanding_rent']

    # ── Step 1: Close old tenancy ─────────────────────────
    old_tenancy.status = Tenancy.Status.TRANSFERRED
    old_tenancy.end_date = transfer_date
    old_tenancy.termination_reason = reason or f'Transferred to {new_unit.unit_number}'
    old_tenancy.save(
        update_fields=['status', 'end_date', 'termination_reason', 'updated_at'])

    # ── Step 2: Free old unit ─────────────────────────────
    old_unit = old_tenancy.unit
    old_unit.status = Unit.Status.VACANT
    old_unit.save(update_fields=['status', 'updated_at'])

    # ── Step 3: Create new tenancy ────────────────────────
    new_tenancy = Tenancy.objects.create(
        organization=old_tenancy.organization,
        tenant=old_tenancy.tenant,
        unit=new_unit,
        start_date=transfer_date,
        monthly_rent=new_monthly_rent,
        required_deposit=new_required_deposit,
        billing_day=old_tenancy.billing_day,
        status=Tenancy.Status.ACTIVE,
        created_by=actor,
    )

    # ── Step 4: Occupy new unit ───────────────────────────
    new_unit.status = Unit.Status.OCCUPIED
    new_unit.save(update_fields=['status', 'updated_at'])

    # ── Step 5: Transfer deposit to new tenancy ───────────
    if old_deposit_held > 0:
        # Close old deposit account with TRANSFER_OUT
        deposit_service.record_movement(
            old_tenancy,
            DepositMovement.Type.TRANSFER_OUT,
            old_deposit_held,
            reason=f'Transfer to unit {new_unit.unit_number}',
            actor=actor, ip=ip,
        )

        # Open new deposit with TRANSFER_IN
        deposit_service.record_movement(
            new_tenancy,
            DepositMovement.Type.TRANSFER_IN,
            old_deposit_held,
            reason=f'Transfer from unit {old_unit.unit_number}',
            actor=actor, ip=ip,
        )

    # ── Step 6: Handle deposit difference ────────────────
    if deposit_difference > 0:
        # Tenant owes a top-up — create a deposit charge
        Charge.objects.create(
            organization=old_tenancy.organization,
            tenancy=new_tenancy,
            charge_type=Charge.Type.OTHER,
            description=(
                f'Deposit top-up: {old_unit.unit_number} '
                f'-> {new_unit.unit_number}'
            ),
            amount=deposit_difference,
            due_date=transfer_date,
            created_by=actor,
        )

    elif deposit_difference < 0:
        # Surplus — handle based on disposition
        surplus = abs(deposit_difference)

        if deposit_disposition == Transfer.DepositDisposition.REFUND:
            # Record refund movement out of new deposit
            deposit_service.record_movement(
                new_tenancy,
                DepositMovement.Type.REFUND,
                surplus,
                reason='Deposit surplus refunded on transfer',
                actor=actor, ip=ip,
            )

        elif deposit_disposition == Transfer.DepositDisposition.RENT_CREDIT:
            # Create a credit charge (negative OTHER) against next rent
            Charge.objects.create(
                organization=old_tenancy.organization,
                tenancy=new_tenancy,
                charge_type=Charge.Type.OTHER,
                description='Deposit surplus credit applied to rent',
                amount=-surplus,
                due_date=transfer_date,
                created_by=actor,
            )

        # HOLD — surplus stays in deposit, nothing extra to do

    # ── Step 7: Carry over outstanding rent charges ───────
    # We leave the charges on the old tenancy for full audit trail.
    # The outstanding_rent_carried field on Transfer records the amount.
    # Staff must collect the outstanding separately — we do NOT
    # silently move charges to avoid confusing the old tenancy ledger.

    # ── Step 8: Create Transfer record ───────────────────
    transfer = Transfer.objects.create(
        organization=old_tenancy.organization,
        old_tenancy=old_tenancy,
        new_tenancy=new_tenancy,
        tenant=old_tenancy.tenant,
        transfer_date=transfer_date,
        old_monthly_rent=old_tenancy.monthly_rent,
        new_monthly_rent=new_monthly_rent,
        old_deposit_held=old_deposit_held,
        new_deposit_required=new_required_deposit,
        deposit_difference=deposit_difference,
        outstanding_rent_carried=outstanding_rent,
        deposit_disposition=deposit_disposition,
        reason=reason,
        notes=notes,
        created_by=actor,
    )

    # ── Step 9: Audit log ─────────────────────────────────
    log_action(
        Action.TENANCY_TRANSFERRED,
        actor=actor,
        organization=old_tenancy.organization,
        obj=transfer,
        before={
            'unit':    old_unit.unit_number,
            'rent':    str(old_tenancy.monthly_rent),
            'deposit': str(old_deposit_held),
        },
        after={
            'unit':               new_unit.unit_number,
            'rent':               str(new_monthly_rent),
            'deposit_required':   str(new_required_deposit),
            'deposit_difference': str(deposit_difference),
            'disposition':        deposit_disposition,
            'outstanding_carried': str(outstanding_rent),
        },
        reason=reason,
        ip=ip,
    )

    return transfer
