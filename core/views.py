from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone
from accounts.permissions import staff_required
from properties.models import Property, Unit
from tenancies.models import Tenancy
from finance.services import arrears_service
from portal.models import MaintenanceRequest, MoveOutRequest, TransferRequest
from finance.models import RentNotice


@login_required
@staff_required
def dashboard(request):
    org = request.user.organization

    # ── Property & unit stats (org-scoped, real) ──────────
    properties = Property.objects.filter(
        organization=org
    ).exclude(status='ARCHIVED') if org else Property.objects.none()

    units = Unit.objects.filter(
        prop__organization=org, is_archived=False
    ) if org else Unit.objects.none()

    total_units = units.count()
    occupied = units.filter(status=Unit.Status.OCCUPIED).count()
    vacant = units.filter(status=Unit.Status.VACANT).count()
    maintenance = units.filter(status=Unit.Status.MAINTENANCE).count()
    occupancy_rate = round((occupied / total_units) *
                           100, 1) if total_units else 0

    # ── Expected rent = Σ monthly_rent of ACTIVE tenancies (real) ──
    active_tenancies = Tenancy.objects.filter(
        organization=org, status=Tenancy.Status.ACTIVE
    ) if org else Tenancy.objects.none()

    expected_rent = active_tenancies.aggregate(
        total=Sum('monthly_rent')
    )['total'] or 0

    # ── Collections (real, from the ledger) ───────────────
    today = timezone.now().date()
    if org:
        collected_this_month = arrears_service.payments_total(
            org, period=(today.year, today.month))
        outstanding = arrears_service.outstanding_total(org)
        todays_payments = arrears_service.payments_total(org, on_date=today)
        pending = arrears_service.pending_payments_count(org)
    else:
        collected_this_month = outstanding = todays_payments = 0
        pending = 0

    collection_rate = (
        round((collected_this_month / expected_rent) * 100, 1)
        if expected_rent else 0
    )

    # ── Recent tenancies (real) ───────────────────────────
    recent_tenancies = (
        Tenancy.objects.filter(organization=org)
        .select_related('tenant', 'unit', 'unit__prop')
        .order_by('-created_at')[:5]
    ) if org else []

    context = {
        'page_title': 'Dashboard',
        'stats': {
            'total_properties':  properties.count(),
            'total_units':       total_units,
            'occupied_units':    occupied,
            'vacant_units':      vacant,
            'maintenance_units': maintenance,
            'occupancy_rate':    occupancy_rate,
            'expected_rent':     expected_rent,
            'collected_rent':    collected_this_month,
            'outstanding_rent':  outstanding,
            'collection_rate':   collection_rate,
            'todays_payments':   todays_payments,
            'pending_payments':  pending,
            'pending_notices':   RentNotice.objects.filter(organization=org, status='SUBMITTED').count() if org else 0,
            'open_maintenance':  MaintenanceRequest.objects.filter(organization=org, status__in=['PENDING', 'ASSIGNED', 'IN_PROGRESS']).count() if org else 0,
            'pending_moveouts':  MoveOutRequest.objects.filter(organization=org, status__in=['PENDING', 'INSPECTION']).count() if org else 0,
            'pending_transfers': TransferRequest.objects.filter(organization=org, status='PENDING').count() if org else 0,
            'action_items':      0,  # sum of above — calculate after
        },
        'recent_tenancies': recent_tenancies,
    }
    return render(request, 'core/dashboard.html', context)
