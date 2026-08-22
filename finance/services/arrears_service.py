"""Arrears listing and collection statistics (all derived from the ledger)."""
from decimal import Decimal
from django.db.models import Sum
from django.utils import timezone

from tenancies.models import Tenancy
from ..models import Charge, Payment


def _charge_qs(organization, prop=None, period=None):
    qs = Charge.objects.filter(organization=organization)
    if prop is not None:
        qs = qs.filter(tenancy__unit__prop=prop)
    if period is not None:
        year, month = period
        qs = qs.filter(period_start__year=year, period_start__month=month)
    return qs


def collection_stats(organization, prop=None, period=None):
    """
    Charge-based expected / collected / outstanding / rate.
    collected = expected − outstanding (allocations can't exceed a charge).
    """
    charges = list(_charge_qs(organization, prop, period))
    expected = sum((c.amount for c in charges), Decimal('0'))
    outstanding = sum((c.balance for c in charges if c.balance > 0), Decimal('0'))
    collected = expected - outstanding
    rate = round((collected / expected * 100), 1) if expected else Decimal('0')
    return {
        'expected':    expected,
        'collected':   collected,
        'outstanding': outstanding,
        'rate':        rate,
    }


def outstanding_total(organization, prop=None):
    charges = _charge_qs(organization, prop)
    return sum((c.balance for c in charges if c.balance > 0), Decimal('0'))


def payments_total(organization, prop=None, period=None, on_date=None):
    """Sum of VERIFIED payments, optionally filtered by property/month/day."""
    qs = Payment.objects.filter(
        organization=organization, status=Payment.Status.VERIFIED)
    if prop is not None:
        qs = qs.filter(tenancy__unit__prop=prop)
    if period is not None:
        year, month = period
        qs = qs.filter(payment_date__year=year, payment_date__month=month)
    if on_date is not None:
        qs = qs.filter(payment_date=on_date)
    return qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')


def pending_payments_count(organization):
    return Payment.objects.filter(
        organization=organization,
        status=Payment.Status.PENDING_VERIFICATION,
    ).count()


def arrears(organization, prop=None):
    """
    Per active tenancy with a positive balance: outstanding amount, oldest
    unpaid due date, last payment date, days outstanding. Sorted worst-first.
    """
    today = timezone.now().date()
    tenancies = (
        Tenancy.objects.filter(organization=organization,
                               status=Tenancy.Status.ACTIVE)
        .select_related('tenant', 'unit', 'unit__prop')
    )
    if prop is not None:
        tenancies = tenancies.filter(unit__prop=prop)

    rows = []
    for tenancy in tenancies:
        charges = list(Charge.objects.filter(tenancy=tenancy))
        outstanding = sum((c.balance for c in charges if c.balance > 0), Decimal('0'))
        if outstanding <= 0:
            continue

        unpaid = [c for c in charges if c.balance > 0]
        oldest_due = min((c.due_date for c in unpaid), default=None)
        last_payment = (
            Payment.objects.filter(tenancy=tenancy,
                                    status=Payment.Status.VERIFIED)
            .order_by('-payment_date')
            .values_list('payment_date', flat=True)
            .first()
        )
        days = (today - oldest_due).days if oldest_due else 0
        rows.append({
            'tenancy':      tenancy,
            'tenant':       tenancy.tenant,
            'unit':         tenancy.unit,
            'outstanding':  outstanding,
            'oldest_due':   oldest_due,
            'last_payment': last_payment,
            'days':         max(0, days),
        })

    rows.sort(key=lambda r: r['outstanding'], reverse=True)
    return rows
