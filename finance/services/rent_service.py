"""Rent charge generation — one RENT charge per active tenancy per period."""
import calendar
from datetime import date
from django.db import transaction
from django.db.models import Q

from audit.services import log_action, Action
from tenancies.models import Tenancy
from ..models import Charge


def rent_for_period(tenancy, period_start):
    """
    The monthly rent applicable for a period: the most recent RentVariation
    effective on/before the period start, else the tenancy's monthly_rent.
    """
    variation = (
        tenancy.rent_variations
        .filter(effective_date__lte=period_start)
        .order_by('-effective_date')
        .first()
    )
    return variation.new_rent if variation else tenancy.monthly_rent


def _due_date(year, month, billing_day):
    days_in_month = calendar.monthrange(year, month)[1]
    return date(year, month, min(billing_day, days_in_month))


@transaction.atomic
def generate_rent_charges(organization, year, month, actor=None, ip=''):
    """
    Create a RENT charge for every active tenancy that was live during the
    given month and doesn't already have one for that period. Idempotent.
    Returns the number of charges created.
    """
    period_start = date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    period_end = date(year, month, days_in_month)

    tenancies = Tenancy.objects.filter(
        organization=organization,
        status=Tenancy.Status.ACTIVE,
        start_date__lte=period_end,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=period_start)
    )

    created = 0
    for tenancy in tenancies:
        already = Charge.objects.filter(
            tenancy=tenancy,
            charge_type=Charge.Type.RENT,
            period_start=period_start,
        ).exists()
        if already:
            continue

        Charge.objects.create(
            organization=organization,
            tenancy=tenancy,
            charge_type=Charge.Type.RENT,
            description=f'Rent — {period_start:%B %Y}',
            period_start=period_start,
            period_end=period_end,
            amount=rent_for_period(tenancy, period_start),
            due_date=_due_date(year, month, tenancy.billing_day),
            created_by=actor,
        )
        created += 1

    log_action(
        Action.RENT_GENERATED, actor=actor, organization=organization,
        after={'period': f'{year}-{month:02d}', 'charges_created': created},
        reason=f'Rent generation for {period_start:%B %Y}', ip=ip,
    )
    return created
