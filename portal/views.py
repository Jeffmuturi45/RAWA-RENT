from django.db.models import Q
from django.db import models
from properties.models import Unit
import logging
from datetime import date
from dateutil.relativedelta import relativedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse, JsonResponse, request
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
# portal/views.py

@tenant_required
def portal_dashboard(request):
    """
    Tenant dashboard showing summary, pending notices, maintenance requests,
    and pending move-out/transfer requests.
    """
    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    # Initialize variables
    summary = None
    pending_notices = []
    open_maintenance = []
    pending_requests = {}
    has_active_tenancy = False

    if tenancy:
        has_active_tenancy = True

        # Get tenant summary (only if there's an active tenancy)
        summary = get_tenant_summary(tenant)

        # Get pending rent notices
        pending_notices = RentNotice.objects.filter(
            tenancy=tenancy,
            status__in=['PENDING', 'SUBMITTED', 'REJECTED'],
        ).order_by('due_date')

        # Get open maintenance requests
        open_maintenance = MaintenanceRequest.objects.filter(
            tenancy=tenancy,
        ).exclude(status__in=['CLOSED', 'CANCELLED']).order_by('-created_at')[:3]

        # Get pending requests
        pending_requests = {
            'moveout': MoveOutRequest.objects.filter(
                tenancy=tenancy,
                status__in=['PENDING', 'INSPECTION']
            ).first(),
            'transfer': TransferRequest.objects.filter(
                tenancy=tenancy,
                status='PENDING'
            ).first(),
        }

    context = {
        'page_title': 'My Account',
        'tenant': tenant,
        'summary': summary,
        'tenancy': tenancy,
        'pending_notices': pending_notices,
        'open_maintenance': open_maintenance,
        'pending_requests': pending_requests,
        'has_active_tenancy': has_active_tenancy,
    }

    return render(request, 'portal/dashboard.html', context)


# ─────────────────────────────────────────
# STATEMENT
# ─────────────────────────────────────────

@tenant_required
def portal_statement(request):
    tenant = request.user.tenant_profile
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

# portal/views.py - Updated portal_payments

@tenant_required
def portal_payments(request):
    """Display payment history with proof upload options."""
    from finance.models import Charge
    from decimal import Decimal

    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    # Get payment history
    payments = Payment.objects.filter(
        tenant=tenant,
    ).order_by('-payment_date').select_related('tenancy')

    # Get outstanding charges and deposit info
    outstanding_charges = []
    deposit_charges = []
    total_outstanding = Decimal('0')
    total_deposit = Decimal('0')
    pending_proofs_count = 0

    if tenancy:
        charges = Charge.objects.filter(tenancy=tenancy)
        for charge in charges:
            # Calculate balance using the property
            balance = charge.balance

            if balance > Decimal('0'):
                # Track pending proofs
                if charge.proof_status == Charge.ProofStatus.PENDING:
                    pending_proofs_count += 1

                # Separate deposit charges from other charges
                if charge.is_deposit_charge:
                    deposit_charges.append({
                        'charge': charge,
                        'balance': balance,
                        'has_proof': bool(charge.proof_of_payment),
                        'proof_status': charge.proof_status,
                        'proof_status_badge': charge.get_proof_status_badge(),
                        'can_upload': charge.can_upload_proof(),
                        'is_deposit': True,
                    })
                    total_deposit += balance
                else:
                    outstanding_charges.append({
                        'charge': charge,
                        'balance': balance,
                        'has_proof': bool(charge.proof_of_payment),
                        'proof_status': charge.proof_status,
                        'proof_status_badge': charge.get_proof_status_badge(),
                        'can_upload': charge.can_upload_proof(),
                        'is_deposit': False,
                    })
                    total_outstanding += balance

    context = {
        'page_title': 'Payment History',
        'tenant': tenant,
        'tenancy': tenancy,
        'payments': payments,
        'outstanding_charges': outstanding_charges,
        'deposit_charges': deposit_charges,
        'has_outstanding': len(outstanding_charges) > 0,
        'has_deposit': len(deposit_charges) > 0,
        'total_outstanding': total_outstanding,
        'total_deposit': total_deposit,
        'pending_proofs_count': pending_proofs_count,
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
    tenant = request.user.tenant_profile
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

    tenant = request.user.tenant_profile
    receipt = get_object_or_404(Receipt, pk=pk, payment__tenant=tenant)

    html_string = render_to_string('portal/receipt_pdf.html', {
        'receipt':      receipt,
        'payment':      receipt.payment,
        'tenant':       tenant,
        'organization': getattr(request.user, 'organization', None),
        'now':          timezone.now(),
    })

    buffer = io.BytesIO()
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
    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    deposit_account = None
    deposit_movements = []

    if tenancy:
        try:
            deposit_account = tenancy.deposit_account
            deposit_movements = deposit_account.movements.order_by(
                'created_at')
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
    tenant = request.user.tenant_profile
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
    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()
    notice = get_object_or_404(
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
        notice.proof_of_payment = proof
        notice.status = RentNotice.Status.SUBMITTED
        notice.proof_uploaded_at = timezone.now()
        notice.save(update_fields=['proof_of_payment',
                    'status', 'proof_uploaded_at'])

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
    tenant = request.user.tenant_profile
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
    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    if not tenancy:
        messages.error(request, 'You have no active tenancy.')
        return redirect('portal:dashboard')

    category = request.POST.get('category', '').strip()
    priority = request.POST.get('priority', 'MEDIUM').strip()
    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    photo = request.FILES.get('photo')

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
    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()
    mr = get_object_or_404(MaintenanceRequest, pk=pk, tenancy=tenancy)

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
    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()
    mr = get_object_or_404(
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

    mr.tenant_rating = rating
    mr.tenant_feedback = request.POST.get('feedback', '').strip()
    mr.status = MaintenanceRequest.Status.CLOSED
    mr.save(update_fields=['tenant_rating', 'tenant_feedback', 'status'])

    messages.success(request, 'Thank you for your feedback.')
    return redirect('portal:maintenance')


# ─────────────────────────────────────────
# MOVE-OUT REQUEST
# ─────────────────────────────────────────

@tenant_required
def portal_moveout(request):
    """Display the move-out request page."""
    from finance.models import Charge
    from django.db import models
    from decimal import Decimal
    from datetime import date, timedelta

    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    existing = None
    has_arrears = False
    arrears_amount = 0
    can_request = True
    block_reason = None
    today = date.today()
    max_future_date = today + timedelta(days=365)

    if tenancy:
        existing = MoveOutRequest.objects.filter(
            tenancy=tenancy,
        ).order_by('-created_at').first()

        # ─────────────────────────────────────────
        # CALCULATE OUTSTANDING ARREARS
        # ─────────────────────────────────────────
        # Charge model has:
        # - amount: total charge amount
        # - allocations: related PaymentAllocation records
        #
        # Balance = amount - sum(allocations.amount)
        outstanding_charges = Decimal('0')

        charges = Charge.objects.filter(tenancy=tenancy)

        for charge in charges:
            # Calculate total allocated/paid amount for this charge
            total_paid = charge.allocations.aggregate(
                total=models.Sum('amount')
            )['total'] or Decimal('0')

            # Calculate balance
            balance = charge.amount - total_paid

            # Only add positive balances (outstanding)
            if balance > Decimal('0'):
                outstanding_charges += balance

        if outstanding_charges > Decimal('0'):
            has_arrears = True
            arrears_amount = outstanding_charges
            can_request = False
            block_reason = f'You have outstanding arrears of KSh {arrears_amount:,.0f}. Please clear all arrears before requesting a move-out.'

        # Check for pending transfer
        if can_request:
            from portal.models import TransferRequest
            active_transfer = TransferRequest.objects.filter(
                tenancy=tenancy,
                status='PENDING'
            ).first()
            if active_transfer:
                can_request = False
                block_reason = 'You have a pending transfer request. Please cancel it before requesting a move-out.'

        # Check for existing pending move-out
        if can_request and existing and existing.status in ['PENDING', 'INSPECTION']:
            can_request = False
            block_reason = f'You already have a {existing.get_status_display().lower()} move-out request. Please wait for the agency to process it.'

    context = {
        'page_title': 'Move-Out Request',
        'tenant': tenant,
        'tenancy': tenancy,
        'existing': existing,
        'has_arrears': has_arrears,
        'arrears_amount': arrears_amount,
        'can_request': can_request,
        'block_reason': block_reason,
        'min_notice_days': 30,
        'today': today,
        'max_future_date': max_future_date,
    }
    return render(request, 'portal/moveout.html', context)


@tenant_required
@require_POST
def portal_moveout_create(request):
    """Tenant submits a move-out request."""
    from datetime import date, timedelta
    from finance.models import Charge
    from decimal import Decimal

    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    # ─────────────────────────────────────────
    # 1. VERIFY ACTIVE TENANCY
    # ─────────────────────────────────────────
    if not tenancy:
        messages.error(request, 'You have no active tenancy.')
        return redirect('portal:dashboard')

    # ─────────────────────────────────────────
    # 2. CHECK FOR EXISTING PENDING REQUEST
    # ─────────────────────────────────────────
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

    # ─────────────────────────────────────────
    # 3. CHECK FOR OUTSTANDING ARREARS
    # ─────────────────────────────────────────
    # Charge model doesn't have status field - check balance instead
    outstanding_charges = Charge.objects.filter(
        tenancy=tenancy
    ).aggregate(
        total_outstanding=models.Sum('balance')
    )['total_outstanding'] or Decimal('0')

    if outstanding_charges > Decimal('0'):
        messages.error(
            request,
            f'You have outstanding arrears of KSh {outstanding_charges:,.0f}. '
            f'Please clear all arrears before requesting a move-out.'
        )
        return redirect('portal:moveout')

    # ─────────────────────────────────────────
    # 4. VALIDATE FORM INPUT
    # ─────────────────────────────────────────
    requested_date_str = request.POST.get('requested_moveout_date', '').strip()
    reason = request.POST.get('reason', '').strip()

    # Validate date
    if not requested_date_str:
        messages.error(request, 'Please select a move-out date.')
        return redirect('portal:moveout')

    try:
        requested_date = date.fromisoformat(requested_date_str)
    except ValueError:
        messages.error(request, 'Invalid date format. Please use YYYY-MM-DD.')
        return redirect('portal:moveout')

    # ─────────────────────────────────────────
    # 5. DATE VALIDATIONS
    # ─────────────────────────────────────────
    today = date.today()
    max_future_date = today + timedelta(days=365)

    if requested_date <= today:
        messages.error(
            request,
            'Move-out date must be in the future. '
            'Please select a date after today.'
        )
        return redirect('portal:moveout')

    if requested_date > max_future_date:
        messages.error(
            request,
            f'Move-out date cannot be more than 1 year in advance. '
            f'Please select a date on or before {max_future_date.strftime("%d %b %Y")}.'
        )
        return redirect('portal:moveout')

    # Validate minimum notice period (30 days)
    min_notice_days = 30
    if (requested_date - today).days < min_notice_days:
        messages.error(
            request,
            f'You must provide at least {min_notice_days} days notice. '
            f'Please select a date at least {min_notice_days} days from today.'
        )
        return redirect('portal:moveout')

    # ─────────────────────────────────────────
    # 6. VALIDATE REASON
    # ─────────────────────────────────────────
    if not reason:
        messages.error(request, 'Please provide a reason for moving out.')
        return redirect('portal:moveout')

    if len(reason) > 2000:
        messages.error(
            request,
            'The reason cannot exceed 2000 characters.'
        )
        return redirect('portal:moveout')

    # ─────────────────────────────────────────
    # 7. CHECK FOR ACTIVE TRANSFER REQUESTS
    # ─────────────────────────────────────────
    from portal.models import TransferRequest

    active_transfer = TransferRequest.objects.filter(
        tenancy=tenancy,
        status='PENDING'
    ).first()

    if active_transfer:
        messages.error(
            request,
            'You have a pending transfer request. '
            'Please cancel it before requesting a move-out.'
        )
        return redirect('portal:moveout')

    # ─────────────────────────────────────────
    # 8. CREATE MOVE-OUT REQUEST WITH TRANSACTION
    # ─────────────────────────────────────────
    try:
        with transaction.atomic():
            mor = MoveOutRequest.objects.create(
                organization=tenancy.organization,
                tenant=tenant,
                tenancy=tenancy,
                requested_moveout_date=requested_date,
                reason=reason,
                status=MoveOutRequest.Status.PENDING,
            )

            # ─────────────────────────────────────────
            # 9. NOTIFY ORGANIZATION ADMINS
            # ─────────────────────────────────────────
            notify_org_admins(
                organization=tenancy.organization,
                message=(
                    f'{tenant.full_name} ({tenancy.unit.unit_number}) has submitted a '
                    f'move-out request for {requested_date.strftime("%d %b %Y")}. '
                    f'Reason: {reason[:100]}{"..." if len(reason) > 100 else ""}'
                ),
                url=f'/finance/moveout-requests/{mor.pk}/',
                level='warning',
                notification_type='MOVEOUT_UPDATE',
            )

            # ─────────────────────────────────────────
            # 10. NOTIFY TENANT (CONFIRMATION)
            # ─────────────────────────────────────────
            from notifications.models import notify

            tenant_user = getattr(tenant, 'user', None)
            if tenant_user:
                notify(
                    recipient=tenant_user,
                    message=(
                        f'Your move-out request has been submitted successfully. '
                        f'Requested date: {requested_date.strftime("%d %b %Y")}. '
                        f'The agency will contact you to schedule an inspection.'
                    ),
                    url='/portal/moveout/',
                    level='success',
                    notification_type='MOVEOUT_UPDATE',
                    organization=tenancy.organization,
                )

    except Exception as e:
        logger.exception(
            f'Failed to create move-out request for tenant {tenant.pk}: {str(e)}')
        messages.error(
            request,
            'We could not submit your move-out request. '
            'Please try again or contact support.'
        )
        return redirect('portal:moveout')

    # ─────────────────────────────────────────
    # 11. SUCCESS MESSAGE
    # ─────────────────────────────────────────
    messages.success(
        request,
        'Move-out request submitted successfully! '
        'The agency will schedule an inspection and contact you with next steps. '
        f'Requested move-out date: {requested_date.strftime("%d %b %Y")}.'
    )
    return redirect('portal:moveout')


@tenant_required
def portal_moveout_detail(request, pk):
    """Shows full inspection checklist progress to tenant."""
    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()
    mor = get_object_or_404(MoveOutRequest, pk=pk, tenancy=tenancy)

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
    """
    Display the tenant's current transfer request or available units
    that can be requested for transfer.
    """
    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    existing = None
    vacant_units = Unit.objects.none()

    # Values prepared for the template.
    # This avoids invalid comparisons/calculations in Django templates.
    deposit_difference_type = None
    deposit_difference_amount = None

    if tenancy:

        # Show the most recent pending transfer request.
        #
        # If your business workflow allows rejected requests to remain
        # visible, change this query accordingly.
        existing = (
            TransferRequest.objects
            .filter(
                tenancy=tenancy,
                status='PENDING',
            )
            .select_related(
                'tenant',
                'tenancy',
                'tenancy__unit',
                'requested_unit',
            )
            .first()
        )

        # Only show units from the same property.
        #
        # Never expose units from another property simply because they
        # are VACANT.
        vacant_units = (
            Unit.objects
            .filter(
                prop=tenancy.unit.prop,
                status='VACANT',
            )
            .exclude(
                pk=tenancy.unit.pk
            )
            .select_related(
                'prop',
                'house_type',
            )
            .order_by('unit_number')
        )

        # Prepare deposit information for the template.
        if existing:

            if existing.deposit_difference > 0:
                deposit_difference_type = 'PAY'
                deposit_difference_amount = existing.deposit_difference

            elif existing.deposit_difference < 0:
                deposit_difference_type = 'REFUND'
                deposit_difference_amount = abs(
                    existing.deposit_difference
                )

            else:
                deposit_difference_type = 'NONE'
                deposit_difference_amount = 0

    context = {
        'page_title': 'Request Unit Transfer',
        'tenant': tenant,
        'tenancy': tenancy,
        'existing': existing,
        'vacant_units': vacant_units,
        'deposit_difference_type': deposit_difference_type,
        'deposit_difference_amount': deposit_difference_amount,
    }

    return render(
        request,
        'portal/transfer.html',
        context
    )


@tenant_required
@require_POST
def portal_transfer_create(request):
    """
    Securely create a transfer request.

    All important validation happens on the server.
    Never trust:
        - requested_unit
        - JavaScript validation
        - hidden form fields
        - browser-provided unit status
    """
    tenant = request.user.tenant_profile
    user = request.user
    tenancy = tenant.get_active_tenancy()

    # ─────────────────────────────────────────
    # 1. VERIFY ACTIVE TENANCY
    # ─────────────────────────────────────────

    if not tenancy:
        messages.error(
            request,
            'You do not have an active tenancy and cannot request a transfer.'
        )
        return redirect('portal:transfer')

    # ─────────────────────────────────────────
    # 2. READ AND VALIDATE FORM INPUT
    # ─────────────────────────────────────────

    unit_id = request.POST.get(
        'requested_unit',
        ''
    ).strip()

    reason = request.POST.get(
        'reason',
        ''
    ).strip()

    # Unit selection is required.

    if not unit_id:
        messages.error(
            request,
            'Please select an available unit.'
        )
        return redirect('portal:transfer')

    # Protect against extremely long text submissions.
    #
    # This should also match your model's field limit where possible.

    if len(reason) > 1000:
        messages.error(
            request,
            'The reason for transfer cannot exceed 1000 characters.'
        )
        return redirect('portal:transfer')

    # ─────────────────────────────────────────
    # 3. VALIDATE UNIT ID FORMAT
    # ─────────────────────────────────────────
    #
    # Unit IDs may be integers or UUIDs depending on your Unit model.
    #
    # Instead of manually converting the ID, Django's queryset lookup
    # safely handles the model's primary key type.
    #
    # Invalid IDs are handled below.

    # ─────────────────────────────────────────
    # 4. PREVENT DUPLICATE PENDING REQUESTS
    # ─────────────────────────────────────────

    existing_request = (
        TransferRequest.objects
        .filter(
            tenancy=tenancy,
            status='PENDING',
        )
        .first()
    )

    if existing_request:
        messages.warning(
            request,
            'You already have a pending transfer request. '
            'Please wait for the agency to review it.'
        )
        return redirect('portal:transfer')

    # ─────────────────────────────────────────
    # 5. CHECK 30-DAY COOLDOWN
    # ─────────────────────────────────────────
    # Admin users can bypass the cooldown

    is_admin = user.is_staff or user.is_superuser or hasattr(
        user, 'organization_admin_profile')

    if not is_admin:
        # Find the most recent completed or approved transfer
        recent_transfer = TransferRequest.objects.filter(
            tenancy=tenancy,
            status__in=[
                TransferRequest.Status.COMPLETED,
                TransferRequest.Status.APPROVED
            ]
        ).order_by('-completed_at', '-updated_at').first()

        if recent_transfer:
            # Get the date to check against
            completed_date = recent_transfer.completed_at or recent_transfer.updated_at

            if completed_date:
                days_since_transfer = (timezone.now() - completed_date).days

                if days_since_transfer < 30:
                    days_remaining = 30 - days_since_transfer
                    messages.error(
                        request,
                        f'You can only request a transfer once every 30 days. '
                        f'Please wait {days_remaining} more days.'
                    )
                    return redirect('portal:transfer')

    # ─────────────────────────────────────────
    # 6. CALCULATE EFFECTIVE DATE
    # ─────────────────────────────────────────

    today = date.today()

    effective_date = (
        today.replace(day=1)
        + relativedelta(months=1)
        - relativedelta(days=1)
    )

    # ─────────────────────────────────────────
    # 7. DATABASE TRANSACTION
    # ─────────────────────────────────────────
    #
    # Lock important rows and re-check all conditions.
    #
    # This helps reduce race conditions where:
    #
    # Tenant A selects Unit 5
    # Tenant B selects Unit 5
    #
    # Both submit requests at almost the same time.
    #
    # The database checks the current state again while processing.

    try:

        with transaction.atomic():

            # Lock the tenant's active tenancy.
            #
            # This ensures the tenancy does not change in the middle
            # of the transfer request process.

            locked_tenancy = (
                type(tenancy).objects
                .select_for_update()
                .select_related('unit', 'unit__prop')
                .get(
                    pk=tenancy.pk,
                    status='ACTIVE',
                )
            )

            # Re-check for a pending transfer request while inside
            # the transaction.

            pending_exists = (
                TransferRequest.objects
                .select_for_update()
                .filter(
                    tenancy=locked_tenancy,
                    status='PENDING',
                )
                .exists()
            )

            if pending_exists:
                messages.warning(
                    request,
                    'A transfer request is already pending for your tenancy.'
                )
                return redirect('portal:transfer')

            # Lock and validate the requested unit.
            #
            # IMPORTANT:
            #
            # We filter by ALL security requirements here.
            #
            # A user cannot simply modify the HTML and submit a unit
            # from another property.

            try:

                requested_unit = (
                    Unit.objects
                    .select_for_update()
                    .select_related(
                        'prop',
                        'house_type',
                    )
                    .get(
                        pk=unit_id,

                        # Must belong to the same property.
                        prop=locked_tenancy.unit.prop,

                        # Must still be vacant.
                        status='VACANT',
                    )
                )

            except (
                Unit.DoesNotExist,
                ValueError,
                TypeError,
            ):

                messages.error(
                    request,
                    'The selected unit is not available for transfer.'
                )

                return redirect('portal:transfer')

            # ─────────────────────────────────────────
            # 8. PREVENT CURRENT UNIT SELECTION
            # ─────────────────────────────────────────

            if requested_unit.pk == locked_tenancy.unit.pk:
                messages.error(
                    request,
                    'You cannot request a transfer to your current unit.'
                )
                return redirect('portal:transfer')

            # ─────────────────────────────────────────
            # 9. CALCULATE DEPOSIT DIFFERENCE
            # ─────────────────────────────────────────

            deposit_diff = (
                requested_unit.deposit_amount
                - locked_tenancy.unit.deposit_amount
            )

            # ─────────────────────────────────────────
            # 10. CREATE TRANSFER REQUEST
            # ─────────────────────────────────────────
            #
            # tenant=tenant is REQUIRED because your TransferRequest
            # table has a non-null tenant_id column.

            tr = TransferRequest.objects.create(
                organization=locked_tenancy.organization,
                tenant=tenant,
                tenancy=locked_tenancy,
                requested_unit=requested_unit,
                requested_date=today,
                reason=reason,
                effective_date=effective_date,
                old_deposit=locked_tenancy.unit.deposit_amount,
                new_deposit=requested_unit.deposit_amount,
                deposit_difference=deposit_diff,
                bypassed_cooldown=is_admin,
                bypassed_by=user if is_admin else None,
                bypassed_at=timezone.now() if is_admin else None,
            )

            # ─────────────────────────────────────────
            # 11. NOTIFY ORGANIZATION ADMINS
            # ─────────────────────────────────────────

            notify_org_admins(
                organization=locked_tenancy.organization,
                message=(
                    f'{tenant.full_name} has requested a transfer from '
                    f'{locked_tenancy.unit.unit_number} to '
                    f'{requested_unit.unit_number}. '
                    f'Deposit difference: KSh {deposit_diff:,.0f}.'
                    f'{" (Admin bypassed 30-day cooldown)" if is_admin else ""}'
                ),
                # <-- FIXED: Changed from /tenancies/ to /finance/
                url=f'/finance/transfer-requests/{tr.pk}/',
                level='info',
                notification_type='TRANSFER_UPDATE',
            )

    except Exception:
        # Log the real exception internally.
        #
        # Do NOT expose database errors to tenants.

        logger.exception(
            'Failed to create transfer request for tenant %s',
            tenant.pk
        )

        messages.error(
            request,
            'We could not submit your transfer request. '
            'Please try again.'
        )

        return redirect('portal:transfer')

    # ─────────────────────────────────────────
    # 12. SUCCESS MESSAGE
    # ─────────────────────────────────────────

    move_in_date = (
        effective_date
        + relativedelta(days=1)
    )

    if is_admin:
        messages.success(
            request,
            f'Transfer request submitted (admin override). '
            f'If approved, the new tenancy will start on '
            f'1st {move_in_date.strftime("%B %Y")}.'
        )

    elif deposit_diff > 0:
        messages.success(
            request,
            f'Transfer request submitted successfully. '
            f'If approved, your new tenancy will start on '
            f'1st {move_in_date.strftime("%B %Y")}. '
            f'An additional deposit of KSh {deposit_diff:,.0f} '
            f'will be required.'
        )

    elif deposit_diff < 0:
        messages.success(
            request,
            f'Transfer request submitted successfully. '
            f'If approved, your new tenancy will start on '
            f'1st {move_in_date.strftime("%B %Y")}. '
            f'A deposit credit of KSh {abs(deposit_diff):,.0f} '
            f'will be applied.'
        )

    else:
        messages.success(
            request,
            f'Transfer request submitted successfully. '
            f'If approved, your new tenancy will start on '
            f'1st {move_in_date.strftime("%B %Y")}. '
            f'No deposit adjustment is required.'
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

# portal/views.py - Add these new views


@tenant_required
def portal_payment_proof_upload(request, charge_pk):
    """
    Tenant uploads proof of payment for a specific charge.
    This is the main payment proof upload that's always visible.
    """
    from finance.models import Charge
    from django.core.exceptions import PermissionDenied

    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    if not tenancy:
        messages.error(request, 'You have no active tenancy.')
        return redirect('portal:payments')

    charge = get_object_or_404(
        Charge,
        pk=charge_pk,
        tenancy=tenancy,
        balance__gt=0  # Only allow upload for charges with balance
    )

    # Prevent upload if already verified
    if charge.proof_status == 'VERIFIED':
        messages.warning(request, 'This charge has already been verified.')
        return redirect('portal:payments')

    if request.method == 'POST':
        proof = request.FILES.get('proof_of_payment')

        if not proof:
            messages.error(request, 'Please select a file to upload.')
            return redirect('portal:payment_proof_upload', charge_pk=charge_pk)

        # Validate file type
        allowed_extensions = ['.jpg', '.jpeg',
                              '.png', '.pdf', '.heic', '.heif']
        import os
        ext = os.path.splitext(proof.name)[1].lower()
        if ext not in allowed_extensions:
            messages.error(
                request,
                'Only JPG, PNG, PDF, or HEIC files are accepted.'
            )
            return redirect('portal:payment_proof_upload', charge_pk=charge_pk)

        # Validate file size (max 10MB)
        if proof.size > 10 * 1024 * 1024:
            messages.error(request, 'File size cannot exceed 10MB.')
            return redirect('portal:payment_proof_upload', charge_pk=charge_pk)

        with transaction.atomic():
            charge.proof_of_payment = proof
            charge.proof_uploaded_at = timezone.now()
            charge.proof_status = 'PENDING'
            charge.proof_verified = False
            charge.save(update_fields=[
                'proof_of_payment', 'proof_uploaded_at',
                'proof_status', 'proof_verified'
            ])

            # Notify admins
            notify_org_admins(
                organization=tenancy.organization,
                message=(
                    f'{tenant.full_name} has uploaded proof of payment '
                    f'for charge #{charge.id} of KSh {charge.balance:,.0f}. '
                    f'Type: {charge.get_charge_type_display()}. '
                    f'Description: {charge.description[:100]}'
                ),
                url=f'/finance/charges/{charge.pk}/verify-proof/',
                level='info',
                notification_type='PAYMENT_RECEIVED',
            )

            # Notify tenant
            tenant_user = getattr(tenant, 'user', None)
            if tenant_user:
                from notifications.models import notify
                notify(
                    recipient=tenant_user,
                    message=(
                        f'Your proof of payment for charge #{charge.id} '
                        f'has been uploaded successfully. '
                        f'We will verify it shortly.'
                    ),
                    url='/portal/payments/',
                    level='success',
                    notification_type='PAYMENT_UPLOADED',
                    organization=tenancy.organization,
                )

        messages.success(
            request,
            'Proof of payment uploaded successfully! '
            'The agency will verify and approve it shortly.'
        )
        return redirect('portal:payments')

    context = {
        'page_title': 'Upload Proof of Payment',
        'tenant': tenant,
        'tenancy': tenancy,
        'charge': charge,
        'charge_type_display': charge.get_charge_type_display(),
    }
    return render(request, 'portal/payment_proof_upload.html', context)

# portal/views.py - Add these views after the moveout views


@tenant_required
def portal_payment_proof_upload(request, charge_pk):
    """
    Tenant uploads proof of payment for a specific charge.
    This is the main payment proof upload that's always visible.
    """
    from finance.models import Charge
    from decimal import Decimal

    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    if not tenancy:
        messages.error(request, 'You have no active tenancy.')
        return redirect('portal:payments')

    # Get the charge - check balance using the property after retrieval
    charge = get_object_or_404(
        Charge.objects.filter(tenancy=tenancy),
        pk=charge_pk
    )

    # Check balance using the property (not a filter)
    if charge.balance <= Decimal('0'):
        messages.warning(request, 'This charge has already been paid.')
        return redirect('portal:payments')

    # Prevent upload if already verified
    if charge.proof_status == Charge.ProofStatus.VERIFIED:
        messages.warning(request, 'This charge has already been verified.')
        return redirect('portal:payments')

    if request.method == 'POST':
        proof = request.FILES.get('proof_of_payment')

        if not proof:
            messages.error(request, 'Please select a file to upload.')
            return redirect('portal:payment_proof_upload', charge_pk=charge_pk)

        # Validate file type
        allowed_extensions = ['.jpg', '.jpeg',
                              '.png', '.pdf', '.heic', '.heif']
        import os
        ext = os.path.splitext(proof.name)[1].lower()
        if ext not in allowed_extensions:
            messages.error(
                request,
                'Only JPG, PNG, PDF, or HEIC files are accepted.'
            )
            return redirect('portal:payment_proof_upload', charge_pk=charge_pk)

        # Validate file size (max 10MB)
        if proof.size > 10 * 1024 * 1024:
            messages.error(request, 'File size cannot exceed 10MB.')
            return redirect('portal:payment_proof_upload', charge_pk=charge_pk)

        with transaction.atomic():
            charge.proof_of_payment = proof
            charge.proof_uploaded_at = timezone.now()
            charge.proof_status = Charge.ProofStatus.PENDING
            charge.proof_verified = False
            charge.save(update_fields=[
                'proof_of_payment', 'proof_uploaded_at',
                'proof_status', 'proof_verified'
            ])

            # Notify admins
            notify_org_admins(
                organization=tenancy.organization,
                message=(
                    f'{tenant.full_name} has uploaded proof of payment '
                    f'for charge #{charge.id} of KSh {charge.balance:,.0f}. '
                    f'Type: {charge.get_charge_type_display()}. '
                    f'Description: {charge.description[:100]}'
                ),
                url=f'/finance/charges/{charge.pk}/verify-proof/',
                level='info',
                notification_type='PAYMENT_RECEIVED',
            )

            # Notify tenant
            tenant_user = getattr(tenant, 'user', None)
            if tenant_user:
                from notifications.models import notify
                notify(
                    recipient=tenant_user,
                    message=(
                        f'Your proof of payment for charge #{charge.id} '
                        f'has been uploaded successfully. '
                        f'We will verify it shortly.'
                    ),
                    url='/portal/payments/',
                    level='success',
                    notification_type='PAYMENT_UPLOADED',
                    organization=tenancy.organization,
                )

        messages.success(
            request,
            'Proof of payment uploaded successfully! '
            'The agency will verify and approve it shortly.'
        )
        return redirect('portal:payments')

    context = {
        'page_title': 'Upload Proof of Payment',
        'tenant': tenant,
        'tenancy': tenancy,
        'charge': charge,
        'charge_type_display': charge.get_charge_type_display(),
        'balance': charge.balance,
    }
    return render(request, 'portal/payment_proof_upload.html', context)


@tenant_required
def portal_moveout_proof_upload(request):
    """
    Special upload for move-out when there are arrears.
    This is only visible when the tenant is moving out and has arrears.
    """
    from finance.models import Charge
    from decimal import Decimal

    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    if not tenancy:
        messages.error(request, 'You have no active tenancy.')
        return redirect('portal:dashboard')

    # Check if there's a pending move-out request
    moveout = MoveOutRequest.objects.filter(
        tenancy=tenancy,
        status__in=['PENDING', 'INSPECTION']
    ).first()

    if not moveout:
        messages.error(request, 'You do not have an active move-out request.')
        return redirect('portal:moveout')

    # Calculate total outstanding charges
    outstanding_charges = Decimal('0')
    charges = Charge.objects.filter(tenancy=tenancy)
    charges_with_balance = []

    for charge in charges:
        balance = charge.balance
        if balance > Decimal('0'):
            outstanding_charges += balance
            charges_with_balance.append({
                'charge': charge,
                'balance': balance,
                'has_proof': bool(charge.proof_of_payment),
                'proof_status': charge.proof_status,
                'proof_status_badge': charge.get_proof_status_badge(),
                'can_upload': charge.can_upload_proof(),
            })

    if outstanding_charges == Decimal('0'):
        messages.info(request, 'You have no outstanding charges.')
        return redirect('portal:moveout')

    if request.method == 'POST':
        proof = request.FILES.get('proof_of_payment')
        charge_id = request.POST.get('charge_id')

        if not proof:
            messages.error(request, 'Please select a file to upload.')
            return redirect('portal:moveout_proof_upload')

        charge = get_object_or_404(
            Charge,
            pk=charge_id,
            tenancy=tenancy,
        )

        if charge.balance <= Decimal('0'):
            messages.warning(request, 'This charge has already been paid.')
            return redirect('portal:moveout_proof_upload')

        # Validate file type
        allowed_extensions = ['.jpg', '.jpeg',
                              '.png', '.pdf', '.heic', '.heif']
        import os
        ext = os.path.splitext(proof.name)[1].lower()
        if ext not in allowed_extensions:
            messages.error(
                request,
                'Only JPG, PNG, PDF, or HEIC files are accepted.'
            )
            return redirect('portal:moveout_proof_upload')

        # Validate file size (max 10MB)
        if proof.size > 10 * 1024 * 1024:
            messages.error(request, 'File size cannot exceed 10MB.')
            return redirect('portal:moveout_proof_upload')

        with transaction.atomic():
            charge.proof_of_payment = proof
            charge.proof_uploaded_at = timezone.now()
            charge.proof_status = Charge.ProofStatus.PENDING
            charge.proof_verified = False
            charge.save(update_fields=[
                'proof_of_payment', 'proof_uploaded_at',
                'proof_status', 'proof_verified'
            ])

            # Check if all charges are now cleared or have proofs uploaded
            all_cleared = True
            for ch in Charge.objects.filter(tenancy=tenancy):
                if ch.balance > Decimal('0') and not ch.proof_of_payment:
                    all_cleared = False
                    break

            # If all charges have proofs uploaded, notify admins
            if all_cleared:
                notify_org_admins(
                    organization=tenancy.organization,
                    message=(
                        f'{tenant.full_name} has uploaded proof of payment '
                        f'for all outstanding charges related to move-out. '
                        f'Please verify all proofs to allow move-out completion.'
                    ),
                    url='/finance/moveout-requests/pending-proofs/',
                    level='success',
                    notification_type='MOVEOUT_UPDATE',
                )

            # Notify admins about this specific upload
            notify_org_admins(
                organization=tenancy.organization,
                message=(
                    f'{tenant.full_name} has uploaded proof of payment '
                    f'for charge #{charge.id} (Move-Out related). '
                    f'Amount: KSh {charge.balance:,.0f}.'
                ),
                url=f'/finance/charges/{charge.pk}/verify-proof/',
                level='warning',
                notification_type='PAYMENT_RECEIVED',
            )

            # Notify tenant
            tenant_user = getattr(tenant, 'user', None)
            if tenant_user:
                from notifications.models import notify
                notify(
                    recipient=tenant_user,
                    message=(
                        f'Your move-out payment proof for charge #{charge.id} '
                        f'has been uploaded. Please wait for verification.'
                    ),
                    url='/portal/moveout/',
                    level='success',
                    notification_type='MOVEOUT_UPDATE',
                    organization=tenancy.organization,
                )

        messages.success(
            request,
            'Move-out payment proof uploaded successfully! '
            'The agency will verify it to complete your move-out.'
        )
        return redirect('portal:moveout')

    context = {
        'page_title': 'Upload Move-Out Payment Proofs',
        'tenant': tenant,
        'tenancy': tenancy,
        'moveout': moveout,
        'charges': charges_with_balance,
        'total_outstanding': outstanding_charges,
        'has_pending_proofs': any(
            c['proof_status'] == 'PENDING' for c in charges_with_balance
        ),
        'all_uploaded': all(
            c['has_proof'] for c in charges_with_balance
        ),
    }
    return render(request, 'portal/moveout_proof_upload.html', context)
