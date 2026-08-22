"""
Derived tenant statement + account summary. Nothing here is stored — the
ledger is computed from charges, payments and adjustments every time.
"""
from decimal import Decimal

from ..models import Charge, Payment, Adjustment


def build_statement(tenancy):
    """
    Return a chronological ledger for a tenancy:
      [{date, description, debit, credit, balance, kind}, ...]
    Running balance is positive when the tenant owes money.
    Deposits are excluded (separate ledger).
    """
    rows = []

    # Debits — charges owed.
    for charge in Charge.objects.filter(tenancy=tenancy):
        rows.append({
            'date': charge.period_start or charge.due_date,
            'description': charge.description or charge.get_charge_type_display(),
            'debit': charge.amount,
            'credit': Decimal('0'),
            'kind': 'charge',
            'sort': 0,
        })

    # Credits — verified payments (excluding the deposit portion).
    for payment in Payment.objects.filter(
            tenancy=tenancy, status=Payment.Status.VERIFIED):
        credit = payment.amount - payment.deposit_allocated
        if credit <= 0:
            continue
        label = payment.get_method_display()
        if payment.reference:
            label += f' ({payment.reference})'
        rows.append({
            'date': payment.payment_date,
            'description': f'Payment — {label}',
            'debit': Decimal('0'),
            'credit': credit,
            'kind': 'payment',
            'sort': 2,
        })

    # Adjustments — signed either way.
    for adj in Adjustment.objects.filter(tenancy=tenancy):
        is_debit = adj.direction == Adjustment.Direction.DEBIT
        rows.append({
            'date': adj.effective_date,
            'description': f'Adjustment — {adj.reason}',
            'debit': adj.amount if is_debit else Decimal('0'),
            'credit': Decimal('0') if is_debit else adj.amount,
            'kind': 'adjustment',
            'sort': 1,
        })

    # Chronological; on the same date show charges, then adjustments, then payments.
    rows.sort(key=lambda r: (r['date'], r['sort']))

    balance = Decimal('0')
    for row in rows:
        balance += row['debit'] - row['credit']
        row['balance'] = balance

    return rows


def account_summary(tenancy):
    """Totals for a tenancy account (all derived)."""
    charges = list(Charge.objects.filter(tenancy=tenancy))
    total_charged = sum((c.amount for c in charges), Decimal('0'))
    outstanding = sum((c.balance for c in charges if c.balance > 0), Decimal('0'))

    adjustments = Adjustment.objects.filter(tenancy=tenancy)
    adj_net = sum((a.signed_amount for a in adjustments), Decimal('0'))

    deposit_balance = Decimal('0')
    deposit_required = Decimal('0')
    account = getattr(tenancy, 'deposit_account', None)
    if account is not None:
        deposit_balance = account.balance
        deposit_required = account.required_amount

    return {
        'total_charged':    total_charged,
        'outstanding':      outstanding + adj_net,
        'deposit_balance':  deposit_balance,
        'deposit_required': deposit_required,
        'deposit_shortfall': max(Decimal('0'), deposit_required - deposit_balance),
    }
