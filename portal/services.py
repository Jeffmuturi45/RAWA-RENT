from decimal import Decimal
from django.db.models import Sum, Q
from finance.models import Charge, Payment, PaymentAllocation, DepositAccount


def get_tenant_summary(tenant):
    """
    Returns a financial summary dict for a tenant's active tenancy.
    All balances derived from ledger records — never from stored fields.
    """
    tenancy = tenant.get_active_tenancy()
    if not tenancy:
        return None

    # ── Charges ───────────────────────────────────────────
    charges = Charge.objects.filter(tenancy=tenancy)

    total_charged = charges.aggregate(
        t=Sum('amount'))['t'] or Decimal('0')

    total_allocated = PaymentAllocation.objects.filter(
        charge__tenancy=tenancy
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    outstanding = total_charged - total_allocated

    # ── Unpaid charges detail ─────────────────────────────
    unpaid_charges = [
        c for c in charges
        if c.status in ('UNPAID', 'PARTIAL', 'OVERDUE')
    ]

    # ── Payments ──────────────────────────────────────────
    payments = Payment.objects.filter(
        tenancy=tenancy,
        status='VERIFIED'
    ).order_by('-payment_date')

    total_paid = payments.aggregate(
        t=Sum('amount'))['t'] or Decimal('0')

    last_payment = payments.first()

    # ── Deposit ───────────────────────────────────────────
    try:
        deposit_account = tenancy.deposit_account
        deposit_held = deposit_account.balance
        deposit_required = deposit_account.required_amount
        deposit_shortfall = deposit_account.shortfall
    except DepositAccount.DoesNotExist:
        deposit_held = Decimal('0')
        deposit_required = tenancy.required_deposit
        deposit_shortfall = deposit_required

    return {
        'tenancy':           tenancy,
        'unit':              tenancy.unit,
        'monthly_rent':      tenancy.monthly_rent,
        'total_charged':     total_charged,
        'total_paid':        total_paid,
        'outstanding':       outstanding,
        'unpaid_charges':    unpaid_charges,
        'last_payment':      last_payment,
        'deposit_held':      deposit_held,
        'deposit_required':  deposit_required,
        'deposit_shortfall': deposit_shortfall,
    }


def get_tenant_statement(tenant, tenancy=None):
    """
    Returns a chronological list of statement entries for a tenancy.
    Each entry has: date, description, debit, credit, running_balance.
    """
    if tenancy is None:
        tenancy = tenant.get_active_tenancy()
    if not tenancy:
        return []

    entries = []

    # ── Charges (debits) ──────────────────────────────────
    for charge in Charge.objects.filter(tenancy=tenancy).order_by('due_date'):
        entries.append({
            'date':        charge.due_date,
            'description': charge.description or charge.get_charge_type_display(),
            'debit':       charge.amount,
            'credit':      None,
            'type':        'charge',
            'status':      charge.status,
            'badge':       charge.get_status_badge(),
        })

    # ── Payments (credits) ────────────────────────────────
    for payment in Payment.objects.filter(
        tenancy=tenancy,
        status='VERIFIED'
    ).order_by('payment_date'):
        entries.append({
            'date':        payment.payment_date,
            'description': f'{payment.get_method_display()} Payment',
            'debit':       None,
            'credit':      payment.amount,
            'type':        'payment',
            'status':      'VERIFIED',
            'badge':       'rw-badge-success',
        })

    # ── Sort by date ──────────────────────────────────────
    entries.sort(key=lambda x: x['date'])

    # ── Running balance ───────────────────────────────────
    running = Decimal('0')
    for entry in entries:
        if entry['debit']:
            running += entry['debit']
        if entry['credit']:
            running -= entry['credit']
        entry['balance'] = running

    return entries
