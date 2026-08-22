"""Deposit ledger operations. Deposits are kept entirely separate from rent."""
from decimal import Decimal
from django.db import transaction

from audit.services import log_action, Action
from ..models import DepositAccount, DepositMovement

# Movement types that increase the deposit balance; others decrease it.
_POSITIVE_TYPES = {
    DepositMovement.Type.RECEIVED,
    DepositMovement.Type.OPENING,
    DepositMovement.Type.TRANSFER_IN,
}


def get_or_create_account(tenancy):
    account, _ = DepositAccount.objects.get_or_create(
        tenancy=tenancy,
        defaults={
            'organization': tenancy.organization,
            'required_amount': tenancy.required_deposit,
        },
    )
    return account


@transaction.atomic
def record_movement(tenancy, movement_type, amount, reason='',
                    related_payment=None, actor=None, ip=''):
    """
    Record a deposit movement. `amount` is a positive magnitude; the sign is
    derived from the movement type and stored signed for a simple sum-balance.
    """
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError('Deposit movement amount must be positive.')

    account = get_or_create_account(tenancy)
    signed = amount if movement_type in _POSITIVE_TYPES else -amount

    movement = DepositMovement.objects.create(
        deposit_account=account,
        movement_type=movement_type,
        amount=signed,
        reason=reason,
        related_payment=related_payment,
        created_by=actor,
    )

    log_action(
        Action.DEPOSIT_MOVED, actor=actor, organization=tenancy.organization,
        obj=account,
        after={'type': movement_type, 'amount': str(signed),
               'balance': str(account.balance)},
        reason=reason, ip=ip,
    )
    return movement
