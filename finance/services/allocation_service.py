"""
Payment → charge allocation. Explains exactly where each shilling went.

Default policy (spec §23): settle the oldest outstanding charges first
(by due date), which naturally clears opening arrears and older rent before
current rent. Any remainder is left as an unallocated credit (advance).
"""
from decimal import Decimal
from django.db import transaction

from ..models import Charge, PaymentAllocation


def _outstanding_charges(tenancy):
    """Unpaid/partly-paid charges for a tenancy, oldest due first."""
    charges = (
        Charge.objects.filter(tenancy=tenancy)
        .order_by('due_date', 'created_at')
    )
    return [c for c in charges if c.balance > 0]


@transaction.atomic
def auto_allocate(payment):
    """
    Allocate the payment's currently-unallocated amount across the tenancy's
    outstanding charges, oldest first. Returns the list of allocations made.
    """
    tenancy = payment.tenancy
    if tenancy is None:
        return []

    remaining = payment.unallocated
    if remaining <= 0:
        return []

    made = []
    for charge in _outstanding_charges(tenancy):
        if remaining <= 0:
            break
        take = min(remaining, charge.balance)
        if take <= 0:
            continue
        made.append(PaymentAllocation.objects.create(
            payment=payment, charge=charge, amount=take,
        ))
        remaining -= take
    return made


@transaction.atomic
def manual_allocate(payment, allocations):
    """
    Apply explicit allocations: {charge_id: amount}. Validates each amount is
    positive, does not exceed the charge's remaining balance, and that the
    total does not exceed the payment's unallocated amount.
    """
    total = Decimal('0')
    resolved = []
    for charge_id, amount in allocations.items():
        amount = Decimal(amount)
        if amount <= 0:
            continue
        charge = Charge.objects.select_for_update().get(
            pk=charge_id, tenancy=payment.tenancy)
        if amount > charge.balance:
            raise ValueError(
                f'Allocation KSh {amount} exceeds the KSh {charge.balance} '
                f'balance on charge "{charge}".')
        resolved.append((charge, amount))
        total += amount

    if total > payment.unallocated:
        raise ValueError(
            f'Allocations (KSh {total}) exceed the unallocated payment '
            f'amount (KSh {payment.unallocated}).')

    made = [
        PaymentAllocation.objects.create(payment=payment, charge=charge, amount=amount)
        for charge, amount in resolved
    ]
    return made
