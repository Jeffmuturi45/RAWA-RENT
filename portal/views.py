import logging
from datetime import date
from dateutil.relativedelta import relativedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db import transaction
from django.views.decorators.http import require_POST

from .decorators import tenant_required
from .services import get_tenant_summary, get_tenant_statement
from finance.models import Payment, DepositAccount, RentNotice
from portal.models import MaintenanceRequest, MoveOutRequest, TransferRequest
from receipts.models import Receipt
from notifications.models import notify, notify_org_admins, Notification

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def _get_org_admins_url(path):
    return path


# ─────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────

@tenant_required
def portal_dashboard(request):
    tenant  = request.user.tenant_profile
    summary = get_tenant_summary(tenant)
    tenancy = tenant.get_active_tenancy()

    # Pending rent notices
    pending_notices = []
    open_maintenance = []
    pending_requests = {}

    if tenancy:
        pending_notices = RentNotice.objects.filter(
            tenancy=tenancy,
            status__in=['PENDING', 'SUBMITTED', 'REJECTED'],
        ).order_by('due_date')

        open_maintenance = MaintenanceRequest.objects.filter(
            tenancy=tenancy,
        ).exclude(status__in=['CLOSED', 'CANCELLED']).order_by('-created_at')[:3]

        pending_requests = {
            'moveout': MoveOutRequest.objects.filter(
                tenancy=tenancy, status__in=['PENDING', 'INSPECTION']
            ).first(),
            'transfer': TransferRequest.objects.filter(
                tenancy=tenancy, status='PENDING'
            ).first(),
        }

    context = {
        'page_title':        'My Account',
        'tenant':            tenant,
        'summary':           summary,
        'tenancy':           tenancy,
        'pending_notices':   pending_notices,
        'open_maintenance':  open_maintenance,
        'pending_requests':  pending_requests,
    }
    return render(request, 'portal/dashboard.html', context)


# ─────────────────────────────────────────
# STATEMENT
# ─────────────────────────────────────────

@tenant_required
def portal_statement(request):
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()
    entries = get_tenant_statement(tenant)
    summary = get_tenant_summary(tenant)

    context = {
        'page_title': 'My Statement',
        'tenant':     tenant,
        'tenancy':    tenancy,
        'entries':    entries,
        'summary':    summary,
    }
    return render(request, 'portal/statement.html', context)


# ─────────────────────────────────────────
# PAYMENTS
# ─────────────────────────────────────────

@tenant_required
def portal_payments(request):
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    payments = Payment.objects.filter(
        tenant=tenant,
    ).order_by('-payment_date').select_related('tenancy')

    context = {
        'page_title': 'Payment History',
        'tenant':     tenant,
        'tenancy':    tenancy,
        'payments':   payments,
    }
    return render(request, 'portal/payments.html', context)


# ─────────────────────────────────────────
# RECEIPTS
# ─────────────────────────────────────────

@tenant_required
def portal_receipts(request):
    tenant = request.user.tenant_profile

    receipts = Receipt.objects.filter(
        payment__tenant=tenant
    ).select_related(
        'payment', 'payment__tenancy', 'payment__tenancy__unit'
    ).order_by('-issued_at')

    context = {
        'page_title': 'My Receipts',
        'tenant':     tenant,
        'receipts':   receipts,
    }
    return render(request, 'portal/receipts.html', context)


@tenant_required
def portal_receipt_detail(request, pk):
    tenant  = request.user.tenant_profile
    receipt = get_object_or_404(Receipt, pk=pk, payment__tenant=tenant)

    context = {
        'page_title': f'Receipt {receipt.receipt_number}',
        'tenant':     tenant,
        'receipt':    receipt,
        'payment':    receipt.payment,
    }
    return render(request, 'portal/receipt_detail.html', context)


@tenant_required
def portal_receipt_pdf(request, pk):
    """
    PDF receipt using xhtml2pdf — no system libraries required on Windows or Linux.
    """
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    import io

    tenant  = request.user.tenant_profile
    receipt = get_object_or_404(Receipt, pk=pk, payment__tenant=tenant)

    html_string = render_to_string('portal/receipt_pdf.html', {
        'receipt':      receipt,
        'payment':      receipt.payment,
        'tenant':       tenant,
        'organization': getattr(request.user, 'organization', None),
        'now':          timezone.now(),
    })

    buffer   = io.BytesIO()
    pisa_status = pisa.CreatePDF(html_string, dest=buffer)

    if pisa_status.err:
        logger.error('PDF generation failed for receipt %s', pk)
        return HttpResponse('PDF generation failed.', status=500)

    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'inline; filename="receipt-{receipt.receipt_number}.pdf"'
    )
    return response


# ─────────────────────────────────────────
# DEPOSIT
# ─────────────────────────────────────────

@tenant_required
def portal_deposit(request):
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    deposit_account  = None
    deposit_movements = []

    if tenancy:
        try:
            deposit_account   = tenancy.deposit_account
            deposit_movements = deposit_account.movements.order_by('created_at')
        except DepositAccount.DoesNotExist:
            pass

    context = {
        'page_title':      'Deposit Account',
        'tenant':          tenant,
        'tenancy':         tenancy,
        'deposit_account': deposit_account,
        'movements':       deposit_movements,
    }
    return render(request, 'portal/deposit.html', context)


# ─────────────────────────────────────────
# PROFILE
# ─────────────────────────────────────────

@tenant_required
def portal_profile(request):
    tenant = request.user.tenant_profile
    context = {
        'page_title': 'My Profile',
        'tenant':     tenant,
    }
    return render(request, 'portal/profile.html', context)


# ─────────────────────────────────────────
# RENT NOTICES  (proof of payment workflow)
# ─────────────────────────────────────────

@tenant_required
def portal_notices(request):
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    notices = []
    if tenancy:
        notices = RentNotice.objects.filter(
            tenancy=tenancy,
        ).order_by('-period_start')

    context = {
        'page_title': 'Rent Notices',
        'tenant':     tenant,
        'tenancy':    tenancy,
        'notices':    notices,
    }
    return render(request, 'portal/notices.html', context)


@tenant_required
@require_POST
def portal_notice_upload(request, pk):
    """Tenant uploads proof of payment for a rent notice."""
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()
    notice  = get_object_or_404(
        RentNotice, pk=pk, tenancy=tenancy,
        status__in=['PENDING', 'REJECTED'],
    )

    proof = request.FILES.get('proof_of_payment')
    if not proof:
        messages.error(request, 'Please select a file to upload.')
        return redirect('portal:notices')

    # Validate file type
    allowed = ['.jpg', '.jpeg', '.png', '.pdf']
    import os
    ext = os.path.splitext(proof.name)[1].lower()
    if ext not in allowed:
        messages.error(request, 'Only JPG, PNG, or PDF files are accepted.')
        return redirect('portal:notices')

    with transaction.atomic():
        notice.proof_of_payment  = proof
        notice.status            = RentNotice.Status.SUBMITTED
        notice.proof_uploaded_at = timezone.now()
        notice.save(update_fields=['proof_of_payment', 'status', 'proof_uploaded_at'])

        # Notify agency admins
        notify_org_admins(
            organization=tenancy.organization,
            message=(
                f'{tenant.full_name} has uploaded proof of payment for '
                f'{notice.period_start.strftime("%B %Y")} rent '
                f'(KSh {notice.amount:,.0f}). Please verify.'
            ),
            url=f'/finance/rent-notices/{notice.pk}/review/',
            level='info',
            notification_type='PAYMENT_RECEIVED',
        )

    messages.success(
        request,
        'Proof of payment uploaded successfully. '
        'The agency will verify and approve shortly.'
    )
    return redirect('portal:notices')


# ─────────────────────────────────────────
# MAINTENANCE REQUESTS
# ─────────────────────────────────────────

@tenant_required
def portal_maintenance(request):
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    requests_qs = []
    if tenancy:
        requests_qs = MaintenanceRequest.objects.filter(
            tenancy=tenancy,
        ).order_by('-created_at')

    context = {
        'page_title':    'Maintenance Requests',
        'tenant':        tenant,
        'tenancy':       tenancy,
        'requests':      requests_qs,
        'categories':    MaintenanceRequest.Category.choices,
        'priorities':    MaintenanceRequest.Priority.choices,
    }
    return render(request, 'portal/maintenance.html', context)


@tenant_required
@require_POST
def portal_maintenance_create(request):
    """Tenant submits a new maintenance request."""
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    if not tenancy:
        messages.error(request, 'You have no active tenancy.')
        return redirect('portal:dashboard')

    category    = request.POST.get('category', '').strip()
    priority    = request.POST.get('priority', 'MEDIUM').strip()
    title       = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    photo       = request.FILES.get('photo')

    if not category or not title or not description:
        messages.error(request, 'Please fill in all required fields.')
        return redirect('portal:maintenance')

    # Validate choices
    valid_categories = [c[0] for c in MaintenanceRequest.Category.choices]
    valid_priorities = [p[0] for p in MaintenanceRequest.Priority.choices]
    if category not in valid_categories or priority not in valid_priorities:
        messages.error(request, 'Invalid category or priority.')
        return redirect('portal:maintenance')

    with transaction.atomic():
        mr = MaintenanceRequest.objects.create(
            organization=tenancy.organization,
            tenancy=tenancy,
            category=category,
            priority=priority,
            title=title,
            description=description,
            photo=photo,
        )

        # Notify agency
        notify_org_admins(
            organization=tenancy.organization,
            message=(
                f'New maintenance request from {tenant.full_name} '
                f'({tenancy.unit}): [{mr.get_priority_display()}] {title}'
            ),
            url=f'/finance/maintenance/{mr.pk}/',
            level='warning' if priority == 'HIGH' else 'info',
            notification_type='MAINTENANCE_UPDATE',
        )

    messages.success(
        request,
        'Maintenance request submitted. The agency will be in touch shortly.'
    )
    return redirect('portal:maintenance')


@tenant_required
def portal_maintenance_detail(request, pk):
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()
    mr      = get_object_or_404(MaintenanceRequest, pk=pk, tenancy=tenancy)

    context = {
        'page_title': f'Request: {mr.title}',
        'tenant':     tenant,
        'mr':         mr,
    }
    return render(request, 'portal/maintenance_detail.html', context)


@tenant_required
@require_POST
def portal_maintenance_rate(request, pk):
    """Tenant rates a resolved maintenance request."""
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()
    mr      = get_object_or_404(
        MaintenanceRequest, pk=pk, tenancy=tenancy,
        status=MaintenanceRequest.Status.RESOLVED,
    )

    try:
        rating = int(request.POST.get('rating', 0))
        if not 1 <= rating <= 5:
            raise ValueError
    except (ValueError, TypeError):
        messages.error(request, 'Rating must be between 1 and 5.')
        return redirect('portal:maintenance_detail', pk=pk)

    mr.tenant_rating   = rating
    mr.tenant_feedback = request.POST.get('feedback', '').strip()
    mr.status          = MaintenanceRequest.Status.CLOSED
    mr.save(update_fields=['tenant_rating', 'tenant_feedback', 'status'])

    messages.success(request, 'Thank you for your feedback.')
    return redirect('portal:maintenance')


# ─────────────────────────────────────────
# MOVE-OUT REQUEST
# ─────────────────────────────────────────

@tenant_required
def portal_moveout(request):
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    existing = None
    if tenancy:
        existing = MoveOutRequest.objects.filter(
            tenancy=tenancy,
        ).order_by('-created_at').first()

    context = {
        'page_title': 'Move-Out Request',
        'tenant':     tenant,
        'tenancy':    tenancy,
        'existing':   existing,
    }
    return render(request, 'portal/moveout.html', context)


@tenant_required
@require_POST
def portal_moveout_create(request):
    """Tenant submits a move-out request."""
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    if not tenancy:
        messages.error(request, 'You have no active tenancy.')
        return redirect('portal:dashboard')

    # Block if already has a pending/inspection request
    existing = MoveOutRequest.objects.filter(
        tenancy=tenancy,
        status__in=['PENDING', 'INSPECTION'],
    ).first()
    if existing:
        messages.warning(
            request,
            'You already have a pending move-out request. '
            'Please wait for the agency to process it.'
        )
        return redirect('portal:moveout')

    requested_date_str = request.POST.get('requested_moveout_date', '').strip()
    reason             = request.POST.get('reason', '').strip()

    try:
        requested_date = date.fromisoformat(requested_date_str)
    except ValueError:
        messages.error(request, 'Invalid move-out date.')
        return redirect('portal:moveout')

    if requested_date <= date.today():
        messages.error(request, 'Move-out date must be in the future.')
        return redirect('portal:moveout')

    with transaction.atomic():
        mor = MoveOutRequest.objects.create(
            organization=tenancy.organization,
            tenancy=tenancy,
            requested_moveout_date=requested_date,
            reason=reason,
        )

        notify_org_admins(
            organization=tenancy.organization,
            message=(
                f'{tenant.full_name} ({tenancy.unit}) has submitted a '
                f'move-out request for {requested_date.strftime("%d %b %Y")}.'
            ),
            url=f'/tenancies/moveout-requests/{mor.pk}/',
            level='warning',
            notification_type='MOVEOUT_UPDATE',
        )

    messages.success(
        request,
        'Move-out request submitted. The agency will schedule an inspection '
        'and contact you with next steps.'
    )
    return redirect('portal:moveout')


@tenant_required
def portal_moveout_detail(request, pk):
    """Shows full inspection checklist progress to tenant."""
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()
    mor     = get_object_or_404(MoveOutRequest, pk=pk, tenancy=tenancy)

    context = {
        'page_title':      'Move-Out Progress',
        'tenant':          tenant,
        'mor':             mor,
        'checklist_items': mor.checklist_items,
    }
    return render(request, 'portal/moveout_detail.html', context)


# ─────────────────────────────────────────
# TRANSFER REQUEST
# ─────────────────────────────────────────

@tenant_required
def portal_transfer(request):
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    existing  = None
    vacant_units = []

    if tenancy:
        existing = TransferRequest.objects.filter(
            tenancy=tenancy,
            status='PENDING',
        ).first()

        # Show vacant units in same property (excluding current unit)
        from properties.models import Unit
        vacant_units = Unit.objects.filter(
            prop=tenancy.unit.prop,
            status='VACANT',
        ).exclude(pk=tenancy.unit.pk).select_related('prop', 'house_type')

    context = {
        'page_title':    'Request Unit Transfer',
        'tenant':        tenant,
        'tenancy':       tenancy,
        'existing':      existing,
        'vacant_units':  vacant_units,
    }
    return render(request, 'portal/transfer.html', context)


@tenant_required
@require_POST
def portal_transfer_create(request):
    """Tenant requests a transfer to a different unit."""
    tenant  = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    if not tenancy:
        messages.error(request, 'You have no active tenancy.')
        return redirect('portal:dashboard')

    # Block if already has a pending request
    if TransferRequest.objects.filter(tenancy=tenancy, status='PENDING').exists():
        messages.warning(
            request, 'You already have a pending transfer request.'
        )
        return redirect('portal:transfer')

    from properties.models import Unit
    unit_id = request.POST.get('requested_unit', '').strip()
    reason  = request.POST.get('reason', '').strip()

    try:
        requested_unit = Unit.objects.get(
            pk=unit_id,
            prop=tenancy.unit.prop,
            status='VACANT',
        )
    except Unit.DoesNotExist:
        messages.error(request, 'Selected unit is not available.')
        return redirect('portal:transfer')

    # Effective date = last day of current month (move-in on 1st of next month)
    today          = date.today()
    effective_date = (today.replace(day=1) + relativedelta(months=1)) - relativedelta(days=1)

    # Calculate deposit difference
    deposit_diff = requested_unit.deposit_amount - tenancy.unit.deposit_amount

    with transaction.atomic():
        tr = TransferRequest.objects.create(
            organization=tenancy.organization,
            tenancy=tenancy,
            requested_unit=requested_unit,
            reason=reason,
            effective_date=effective_date,
            deposit_difference=deposit_diff,
        )

        notify_org_admins(
            organization=tenancy.organization,
            message=(
                f'{tenant.full_name} has requested a transfer from '
                f'{tenancy.unit.unit_number} to {requested_unit.unit_number}. '
                f'Deposit difference: KSh {deposit_diff:,.0f}.'
            ),
            url=f'/tenancies/transfer-requests/{tr.pk}/',
            level='info',
            notification_type='TRANSFER_UPDATE',
        )

    messages.success(
        request,
        f'Transfer request submitted. If approved, your move-in date will be '
        f'1st {(effective_date + relativedelta(days=1)).strftime("%B %Y")}. '
        f'The deposit difference of KSh {deposit_diff:,.0f} will be applied.'
        if deposit_diff != 0 else
        'Transfer request submitted. The agency will review and contact you.'
    )
    return redirect('portal:transfer')


# ─────────────────────────────────────────
# NOTIFICATIONS (AJAX mark-read)
# ─────────────────────────────────────────

@tenant_required
def portal_notifications(request):
    notifications = Notification.objects.filter(
        recipient=request.user,
    ).order_by('-created_at')[:50]

    context = {
        'page_title':     'Notifications',
        'notifications':  notifications,
    }
    return render(request, 'portal/notifications.html', context)


@require_POST
def portal_notification_mark_read(request, pk):
    """AJAX endpoint — mark one notification as read."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not notif.is_read:
        notif.is_read = True
        notif.save(update_fields=['is_read'])

    return JsonResponse({'status': 'ok'})


@require_POST
def portal_notifications_mark_all_read(request):
    """AJAX endpoint — mark all notifications as read."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    Notification.objects.filter(
        recipient=request.user, is_read=False
    ).update(is_read=True)

    return JsonResponse({'status': 'ok'})