"""
Move-out workflow service.

Handles formal end of tenancy:
  1. Validates tenancy is active
  2. Records inspection checklist
  3. Calculates deposit settlement
  4. Closes tenancy
  5. Frees unit
  6. Creates MoveOut record
  7. Audit logs everything
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from audit.services import log_action, Action
from finance.models import DepositMovement
from finance.services import deposit_service
from tenancies.models import Tenancy, MoveOut


class MoveOutError(Exception):
    """Raised when a move-out cannot proceed."""


def calculate_moveout_summary(tenancy):
    """
    Returns a financial summary for the move-out review screen.
    Show this to the manager before confirming.
    """
    from finance.models import DepositAccount, Charge

    try:
        deposit_held = tenancy.deposit_account.balance
    except DepositAccount.DoesNotExist:
        deposit_held = Decimal('0')

    outstanding_charges = [
        c for c in Charge.objects.filter(tenancy=tenancy)
        if c.balance > 0
    ]
    outstanding_rent = sum(
        (c.balance for c in outstanding_charges), Decimal('0')
    )

    refundable = max(Decimal('0'), deposit_held - outstanding_rent)

    return {
        'deposit_held':        deposit_held,
        'outstanding_rent':    outstanding_rent,
        'outstanding_charges': outstanding_charges,
        'damage_deductions':   Decimal('0'),  # staff fills this in
        'deposit_refundable':  refundable,
    }


@transaction.atomic
def execute_moveout(
    *,
    tenancy,
    notice_date,
    moveout_date,
    keys_returned,
    walls_condition,
    windows_condition,
    plumbing_condition,
    electrical_condition,
    general_condition,
    inspection_notes='',
    damage_deductions=0,
    deposit_settlement,
    reason='',
    notes='',
    actor=None,
    ip='',
):
    """
    Executes the full move-out workflow atomically.
    Returns the MoveOut record.
    """
    from properties.models import Unit
    from finance.models import DepositAccount, Charge

    # ── Validation ────────────────────────────────────────
    if tenancy.status != Tenancy.Status.ACTIVE:
        raise MoveOutError('Only active tenancies can be ended.')

    damage_deductions = Decimal(damage_deductions or 0)
    if damage_deductions < 0:
        raise MoveOutError('Damage deductions cannot be negative.')

    # ── Financial snapshot ────────────────────────────────
    try:
        deposit_held = tenancy.deposit_account.balance
    except DepositAccount.DoesNotExist:
        deposit_held = Decimal('0')

    outstanding_charges = [
        c for c in Charge.objects.filter(tenancy=tenancy)
        if c.balance > 0
    ]
    outstanding_rent = sum(
        (c.balance for c in outstanding_charges), Decimal('0')
    )

    total_deductions = outstanding_rent + damage_deductions
    deposit_refundable = max(Decimal('0'), deposit_held - total_deductions)

    # ── Step 1: Close tenancy ─────────────────────────────
    tenancy.status           = Tenancy.Status.ENDED
    tenancy.end_date         = moveout_date
    tenancy.termination_reason = reason or 'Tenant moved out'
    tenancy.save(update_fields=[
        'status', 'end_date', 'termination_reason', 'updated_at'
    ])

    # ── Step 2: Free the unit ─────────────────────────────
    unit        = tenancy.unit
    unit.status = Unit.Status.VACANT
    unit.save(update_fields=['status', 'updated_at'])

    # ── Step 3: Record deposit settlement movement ────────
    if damage_deductions > 0 and deposit_held > 0:
        deduct = min(damage_deductions, deposit_held)
        deposit_service.record_movement(
            tenancy,
            DepositMovement.Type.DEDUCTION,
            deduct,
            reason=f'Damage deductions on move-out: {inspection_notes or ""}',
            actor=actor, ip=ip,
        )

    if deposit_refundable > 0:
        deposit_service.record_movement(
            tenancy,
            DepositMovement.Type.REFUND,
            deposit_refundable,
            reason='Deposit refund on move-out',
            actor=actor, ip=ip,
        )

    # ── Step 4: Create MoveOut record ────────────────────
    moveout = MoveOut.objects.create(
        organization         = tenancy.organization,
        tenancy              = tenancy,
        tenant               = tenancy.tenant,
        notice_date          = notice_date,
        moveout_date         = moveout_date,
        keys_returned        = keys_returned,
        walls_condition      = walls_condition,
        windows_condition    = windows_condition,
        plumbing_condition   = plumbing_condition,
        electrical_condition = electrical_condition,
        general_condition    = general_condition,
        inspection_notes     = inspection_notes,
        outstanding_rent     = outstanding_rent,
        damage_deductions    = damage_deductions,
        deposit_held         = deposit_held,
        deposit_refundable   = deposit_refundable,
        deposit_settlement   = deposit_settlement,
        reason               = reason,
        notes                = notes,
        created_by           = actor,
    )

    # ── Step 5: Audit log ─────────────────────────────────
    log_action(
        Action.TENANCY_ENDED,
        actor=actor,
        organization=tenancy.organization,
        obj=moveout,
        before={'status': Tenancy.Status.ACTIVE},
        after={
            'status':             Tenancy.Status.ENDED,
            'deposit_held':       str(deposit_held),
            'outstanding_rent':   str(outstanding_rent),
            'damage_deductions':  str(damage_deductions),
            'deposit_refundable': str(deposit_refundable),
            'settlement':         deposit_settlement,
        },
        reason=reason,
        ip=ip,
    )

    return moveout