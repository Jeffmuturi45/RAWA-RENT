from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from django.views.decorators.http import require_POST
from decimal import Decimal

from accounts.permissions import require_capability, Cap
from audit.services import get_client_ip, log_action, Action
from tenancies.models import Tenancy
from properties.models import Property
from notifications.models import notify_org_admins, notify, Notification

from .models import Payment, Charge
from .forms import (
    PaymentForm, ChargeForm, AdjustmentForm, GenerateRentForm,
    VerifyPaymentForm, RejectPaymentForm,
)
from finance.models import RentNotice
from portal.models import MaintenanceRequest, MoveOutRequest, TransferRequest
from .services import payment_service
from .services.payment_service import DuplicatePaymentError
from .services import rent_service, statement_service, arrears_service


# ─────────────────────────────────────────
# PAYMENTS
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_FINANCE)
def payment_list(request):
    org = request.user.organization
    query = request.GET.get('q', '')
    method = request.GET.get('method', '')

    payments = Payment.objects.filter(organization=org).select_related(
        'tenant', 'tenancy', 'tenancy__unit', 'tenancy__unit__prop')

    if query:
        payments = payments.filter(
            Q(tenant__full_name__icontains=query) |
            Q(reference__icontains=query)
        )
    if method:
        payments = payments.filter(method=method)

    context = {
        'page_title':     'Payments',
        'payments':       payments,
        'query':          query,
        'selected_method': method,
        'method_choices': Payment.Method.choices,
        'total':          payments.count(),
    }
    return render(request, 'finance/payment_list.html', context)


@login_required
@require_capability(Cap.VIEW_FINANCE)
def payment_detail(request, pk):
    org = request.user.organization
    payment = get_object_or_404(
        Payment.objects.select_related('tenant', 'tenancy', 'tenancy__unit',
                                       'tenancy__unit__prop', 'created_by'),
        pk=pk, organization=org)
    allocations = payment.allocations.select_related('charge')
    deposit_movements = payment.deposit_movements.all()

    context = {
        'page_title':        f'Payment — {payment.tenant.full_name}',
        'payment':           payment,
        'allocations':       allocations,
        'deposit_movements': deposit_movements,
    }
    return render(request, 'finance/payment_detail.html', context)


@login_required
@require_capability(Cap.RECORD_PAYMENT)
def payment_record(request):
    """
    Record a payment CLAIM (spec §19/§20). Nothing is allocated until a
    different authorised user verifies it against the M-Pesa statement.
    """
    org = request.user.organization

    if request.method == 'POST':
        form = PaymentForm(request.POST, organization=org)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                payment = payment_service.record_payment_claim(
                    organization=org,
                    tenant=cd['tenant'],
                    amount=cd['amount'],
                    payment_date=cd['payment_date'],
                    method=cd['method'],
                    reference=cd['reference'],
                    deposit_amount=cd['deposit_amount'] or 0,
                    notes=cd['notes'],
                    actor=request.user,
                    ip=get_client_ip(request),
                )
            except DuplicatePaymentError as e:
                form.add_error('reference', str(e))
            except ValueError as e:
                form.add_error(None, str(e))
            else:
                notify_org_admins(
                    org,
                    f'Payment claim of KSh {payment.amount:.0f} for '
                    f'{payment.tenant.full_name} awaits verification.',
                    url=reverse('finance:payment_detail', args=[payment.pk]),
                    level=Notification.Level.WARNING,
                    actor=request.user,
                )
                messages.success(
                    request,
                    f'Payment claim of KSh {payment.amount:.0f} recorded. '
                    f'It must be verified before it affects the ledger.')
                return redirect('finance:payment_detail', pk=payment.pk)
    else:
        initial = {}
        tenant_id = request.GET.get('tenant')
        if tenant_id:
            initial['tenant'] = tenant_id
        form = PaymentForm(organization=org, initial=initial)

    context = {
        'page_title': 'Record Payment',
        'form':       form,
    }
    return render(request, 'finance/payment_form.html', context)


@login_required
@require_capability(Cap.VIEW_FINANCE)
def verification_queue(request):
    org = request.user.organization
    claims = Payment.objects.filter(
        organization=org, status=Payment.Status.PENDING_VERIFICATION
    ).select_related('tenant', 'tenancy', 'tenancy__unit',
                     'tenancy__unit__prop', 'created_by')

    context = {
        'page_title': 'Pending Verification',
        'claims':     claims,
        'total':      claims.count(),
    }
    return render(request, 'finance/verification_queue.html', context)


@login_required
@require_capability(Cap.VERIFY_PAYMENT)
def payment_verify(request, pk):
    """Verify a pending claim — requires the verifier's financial PIN (§20)."""
    org = request.user.organization
    payment = get_object_or_404(
        Payment.objects.select_related('tenant', 'tenancy', 'created_by'),
        pk=pk, organization=org)

    is_own_claim = payment.created_by_id == request.user.pk
    has_pin = request.user.has_financial_pin()

    if request.method == 'POST':
        form = VerifyPaymentForm(request.POST)
        if form.is_valid():
            try:
                payment_service.verify_payment(
                    payment, actor=request.user,
                    pin=form.cleaned_data['pin'],
                    deposit_amount=form.cleaned_data['deposit_amount'] or 0,
                    ip=get_client_ip(request),
                )
            except payment_service.SelfVerificationError as e:
                form.add_error(None, str(e))
            except payment_service.InvalidPinError as e:
                form.add_error('pin', str(e))
            except (payment_service.InvalidStateError, ValueError) as e:
                form.add_error(None, str(e))
            else:
                payment.refresh_from_db()
                if payment.created_by:
                    notify(payment.created_by,
                           f'Your payment claim of KSh {payment.amount:.0f} for '
                           f'{payment.tenant.full_name} was verified.',
                           url=reverse('finance:payment_detail',
                                       args=[payment.pk]),
                           level=Notification.Level.SUCCESS,
                           actor=request.user)
                messages.success(
                    request,
                    f'Payment verified — KSh {payment.total_allocated:.0f} allocated, '
                    f'KSh {payment.unallocated:.0f} on account.')
                return redirect('finance:payment_detail', pk=payment.pk)
    else:
        form = VerifyPaymentForm()

    context = {
        'page_title':   'Verify Payment',
        'payment':      payment,
        'form':         form,
        'is_own_claim': is_own_claim,
        'has_pin':      has_pin,
        'outstanding_charges': [
            c for c in Charge.objects.filter(tenancy=payment.tenancy)
            if c.balance > 0
        ] if payment.tenancy else [],
    }
    return render(request, 'finance/payment_verify.html', context)


@login_required
@require_capability(Cap.VERIFY_PAYMENT)
def payment_reject(request, pk):
    org = request.user.organization
    payment = get_object_or_404(Payment, pk=pk, organization=org)

    if request.method == 'POST':
        form = RejectPaymentForm(request.POST)
        if form.is_valid():
            try:
                payment_service.reject_payment(
                    payment, actor=request.user,
                    reason=form.cleaned_data['reason'],
                    ip=get_client_ip(request))
            except (payment_service.InvalidStateError, ValueError) as e:
                form.add_error(None, str(e))
            else:
                if payment.created_by:
                    notify(payment.created_by,
                           f'Your payment claim of KSh {payment.amount:.0f} was rejected.',
                           url=reverse('finance:payment_detail',
                                       args=[payment.pk]),
                           level=Notification.Level.DANGER,
                           actor=request.user)
                messages.success(request, 'Payment claim rejected.')
                return redirect('finance:payment_detail', pk=payment.pk)
    else:
        form = RejectPaymentForm()

    return render(request, 'finance/payment_reject.html', {
        'page_title': 'Reject Payment',
        'payment':    payment,
        'form':       form,
    })


# ─────────────────────────────────────────
# STATEMENT
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_FINANCE)
def tenant_statement(request, tenancy_pk):
    org = request.user.organization
    tenancy = get_object_or_404(
        Tenancy.objects.select_related('tenant', 'unit', 'unit__prop'),
        pk=tenancy_pk, organization=org)

    context = {
        'page_title': f'Statement — {tenancy.tenant.full_name}',
        'tenancy':    tenancy,
        'rows':       statement_service.build_statement(tenancy),
        'summary':    statement_service.account_summary(tenancy),
    }
    return render(request, 'finance/statement.html', context)


# ─────────────────────────────────────────
# CHARGES & ADJUSTMENTS
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.MANAGE_FINANCE)
def charge_add(request, tenancy_pk):
    org = request.user.organization
    tenancy = get_object_or_404(Tenancy, pk=tenancy_pk, organization=org)

    if request.method == 'POST':
        form = ChargeForm(request.POST)
        if form.is_valid():
            charge = form.save(commit=False)
            charge.organization = org
            charge.tenancy = tenancy
            charge.created_by = request.user
            charge.save()
            log_action(
                Action.CHARGE_CREATED, actor=request.user, organization=org,
                obj=charge, after={'type': charge.charge_type,
                                   'amount': str(charge.amount)},
                ip=get_client_ip(request))
            messages.success(request, 'Charge added.')
            return redirect('finance:tenant_statement', tenancy_pk=tenancy.pk)
    else:
        form = ChargeForm()

    context = {
        'page_title': f'Add Charge — {tenancy.tenant.full_name}',
        'form':       form,
        'tenancy':    tenancy,
    }
    return render(request, 'finance/charge_form.html', context)


@login_required
@require_capability(Cap.MANAGE_FINANCE)
def adjustment_add(request, tenancy_pk):
    org = request.user.organization
    tenancy = get_object_or_404(Tenancy, pk=tenancy_pk, organization=org)

    if request.method == 'POST':
        form = AdjustmentForm(request.POST)
        if form.is_valid():
            adj = form.save(commit=False)
            adj.organization = org
            adj.tenancy = tenancy
            adj.created_by = request.user
            adj.save()
            log_action(
                Action.ADJUSTMENT_CREATED, actor=request.user, organization=org,
                obj=adj, after={'direction': adj.direction,
                                'amount': str(adj.amount)},
                reason=adj.reason, ip=get_client_ip(request))
            messages.success(request, 'Adjustment recorded.')
            return redirect('finance:tenant_statement', tenancy_pk=tenancy.pk)
    else:
        form = AdjustmentForm()

    context = {
        'page_title': f'Add Adjustment — {tenancy.tenant.full_name}',
        'form':       form,
        'tenancy':    tenancy,
    }
    return render(request, 'finance/adjustment_form.html', context)


# ─────────────────────────────────────────
# ARREARS
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_FINANCE)
def arrears_dashboard(request):
    org = request.user.organization
    property_id = request.GET.get('property', '')

    prop = None
    if property_id:
        prop = Property.objects.filter(
            pk=property_id, organization=org).first()

    rows = arrears_service.arrears(org, prop=prop)
    total_outstanding = sum((r['outstanding'] for r in rows), 0)

    context = {
        'page_title':        'Arrears',
        'rows':              rows,
        'total_outstanding': total_outstanding,
        'properties':        Property.objects.filter(organization=org)
                             .exclude(status='ARCHIVED').order_by('name'),
        'selected_property': property_id,
    }
    return render(request, 'finance/arrears.html', context)


# ─────────────────────────────────────────
# RENT GENERATION
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.MANAGE_FINANCE)
def generate_rent(request):
    org = request.user.organization

    if request.method == 'POST':
        form = GenerateRentForm(request.POST)
        if form.is_valid():
            year = form.cleaned_data['year']
            month = int(form.cleaned_data['month'])
            count = rent_service.generate_rent_charges(
                org, year, month, actor=request.user,
                ip=get_client_ip(request))
            if count:
                messages.success(request, f'{count} rent charge(s) generated.')
            else:
                messages.info(
                    request, 'No new rent charges — already generated for that month.')
            return redirect('finance:payment_list')
    else:
        form = GenerateRentForm()

    context = {
        'page_title': 'Generate Rent',
        'form':       form,
    }
    return render(request, 'finance/generate_rent.html', context)


# ─────────────────────────────────────────
# RENT NOTICES — admin review queue
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_FINANCE)
def rent_notice_list(request):
    """All rent notices across org — filterable by status."""
    org = request.user.organization
    status = request.GET.get('status', '')
    prop = request.GET.get('property', '')

    notices = RentNotice.objects.filter(
        organization=org
    ).select_related(
        'tenancy', 'tenancy__tenant',
        'tenancy__unit', 'tenancy__unit__prop',
    ).order_by('-period_start')

    if status:
        notices = notices.filter(status=status)
    if prop:
        notices = notices.filter(tenancy__unit__prop__id=prop)

    context = {
        'page_title':      'Rent Notices',
        'notices':         notices,
        'status_choices':  RentNotice.Status.choices,
        'selected_status': status,
        'properties':      Property.objects.filter(
            organization=org).exclude(status='ARCHIVED'),
        'selected_property': prop,
        'counts': {
            'pending':   notices.filter(status='PENDING').count(),
            'submitted': notices.filter(status='SUBMITTED').count(),
            'approved':  notices.filter(status='APPROVED').count(),
            'rejected':  notices.filter(status='REJECTED').count(),
        },
    }
    return render(request, 'finance/rent_notice_list.html', context)


@login_required
@require_capability(Cap.VERIFY_PAYMENT)
def rent_notice_review(request, pk):
    """
    Agency reviews submitted proof and approves or rejects.
    On approval: creates a verified Payment + allocates it against the Charge.
    """
    from finance.models import RentNotice, Payment, PaymentAllocation
    org = request.user.organization
    notice = get_object_or_404(
        RentNotice, pk=pk, organization=org, status='SUBMITTED')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'approve':
            with transaction.atomic():
                # Create a verified payment
                payment = Payment.objects.create(
                    organization=org,
                    tenant=notice.tenancy.tenant,
                    tenancy=notice.tenancy,
                    amount=notice.amount,
                    payment_date=timezone.now().date(),
                    method=Payment.Method.OTHER,
                    status=Payment.Status.VERIFIED,
                    notes=f'Auto-approved from rent notice {notice.pk}',
                    proof_of_payment=notice.proof_of_payment,
                    verified_by=request.user,
                    verified_at=timezone.now(),
                    created_by=request.user,
                )
                # Allocate against the charge
                if notice.charge:
                    PaymentAllocation.objects.create(
                        payment=payment,
                        charge=notice.charge,
                        amount=min(notice.amount, notice.charge.balance),
                    )
                # Update notice
                notice.status = RentNotice.Status.APPROVED
                notice.approved_by = request.user
                notice.approved_at = timezone.now()
                notice.save(update_fields=[
                            'status', 'approved_by', 'approved_at'])

                # Notify tenant
                tenant_user = getattr(notice.tenancy.tenant, 'user', None)
                if tenant_user:
                    notify(
                        recipient=tenant_user,
                        message=(
                            f'Your rent payment of KSh {notice.amount:,.0f} '
                            f'for {notice.period_start.strftime("%B %Y")} '
                            f'has been approved.'
                        ),
                        url='/portal/notices/',
                        level='success',
                        notification_type='PAYMENT_VERIFIED',
                        organization=org,
                    )

            messages.success(
                request, 'Rent notice approved and payment recorded.')
            return redirect('finance:rent_notice_list')

        elif action == 'reject':
            rejection_notes = request.POST.get('rejection_notes', '').strip()
            notice.status = RentNotice.Status.REJECTED
            notice.rejection_notes = rejection_notes
            notice.save(update_fields=['status', 'rejection_notes'])

            tenant_user = getattr(notice.tenancy.tenant, 'user', None)
            if tenant_user:
                notify(
                    recipient=tenant_user,
                    message=(
                        f'Your proof of payment for '
                        f'{notice.period_start.strftime("%B %Y")} rent '
                        f'was rejected. Reason: {rejection_notes or "See agency."} '
                        f'Please resubmit.'
                    ),
                    url='/portal/notices/',
                    level='danger',
                    notification_type='PAYMENT_REJECTED',
                    organization=org,
                )

            messages.warning(
                request, 'Rent notice rejected. Tenant has been notified.')
            return redirect('finance:rent_notice_list')

    context = {
        'page_title': f'Review Notice — {notice.tenancy.tenant.full_name}',
        'notice':     notice,
    }
    return render(request, 'finance/rent_notice_review.html', context)


# ─────────────────────────────────────────
# ADMIN GENERATE RENTS BUTTON
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.MANAGE_FINANCE)
@require_POST
def trigger_rent_generation(request):
    """Admin button — queues the Celery task for this org."""
    from finance.tasks import admin_generate_rents_for_org
    org = request.user.organization
    admin_generate_rents_for_org.delay(
        organization_id=str(org.id),
        triggered_by_user_id=str(request.user.id),
    )
    messages.success(
        request,
        'Rent generation has been queued. '
        'You will receive a notification when it completes.'
    )
    return redirect('finance:rent_notice_list')


# ─────────────────────────────────────────
# MAINTENANCE REQUESTS — admin views
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_FINANCE)
def maintenance_list(request):
    from portal.models import MaintenanceRequest
    org = request.user.organization
    status = request.GET.get('status', '')
    priority = request.GET.get('priority', '')
    prop = request.GET.get('property', '')

    qs = MaintenanceRequest.objects.filter(
        organization=org
    ).select_related(
        'tenant', 'tenancy', 'tenancy__unit', 'tenancy__unit__prop'
    ).order_by('-created_at')

    if status:
        qs = qs.filter(status=status)
    if priority:
        qs = qs.filter(priority=priority)
    if prop:
        qs = qs.filter(tenancy__unit__prop__id=prop)

    context = {
        'page_title':        'Maintenance Requests',
        'requests':          qs,
        'status_choices':    MaintenanceRequest.Status.choices,
        'priority_choices':  MaintenanceRequest.Priority.choices,
        'selected_status':   status,
        'selected_priority': priority,
        'properties':        Property.objects.filter(
            organization=org).exclude(status='ARCHIVED'),
        'selected_property': prop,
        'open_count':   qs.filter(status='PENDING').count(),
        'urgent_count': qs.filter(priority='URGENT',
                                  status__in=['PENDING', 'ASSIGNED', 'IN_PROGRESS']).count(),
    }
    return render(request, 'finance/maintenance_list.html', context)


@login_required
@require_capability(Cap.VIEW_FINANCE)
def maintenance_detail(request, pk):
    from portal.models import MaintenanceRequest
    org = request.user.organization
    mr = get_object_or_404(MaintenanceRequest, pk=pk, organization=org)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'assign':
            mr.assigned_to = request.POST.get('assigned_to', '').strip()
            mr.assigned_at = timezone.now()
            mr.status = MaintenanceRequest.Status.ASSIGNED
            mr.staff_notes = request.POST.get('staff_notes', '').strip()
            mr.save(update_fields=[
                'assigned_to', 'assigned_at', 'status', 'staff_notes', 'updated_at'])
            _notify_tenant_maintenance(mr, org,
                                       f'Your maintenance request "{mr.title}" has been assigned to '
                                       f'{mr.assigned_to} and will be attended to shortly.')
            messages.success(request, 'Request assigned.')

        elif action == 'in_progress':
            mr.status = MaintenanceRequest.Status.IN_PROGRESS
            mr.staff_notes = request.POST.get('staff_notes', mr.staff_notes)
            mr.save(update_fields=['status', 'staff_notes', 'updated_at'])
            _notify_tenant_maintenance(mr, org,
                                       f'Your maintenance request "{mr.title}" is now in progress.')
            messages.success(request, 'Status updated to In Progress.')

        elif action == 'resolve':
            notes = request.POST.get('resolution_notes', '').strip()
            mr.mark_resolved(user=request.user, notes=notes)
            _notify_tenant_maintenance(mr, org,
                                       f'Your maintenance request "{mr.title}" has been resolved. '
                                       f'Please rate the service in your portal.')
            messages.success(request, 'Request marked as resolved.')

        elif action == 'reject':
            mr.status = MaintenanceRequest.Status.REJECTED
            mr.staff_notes = request.POST.get('staff_notes', '').strip()
            mr.save(update_fields=['status', 'staff_notes', 'updated_at'])
            _notify_tenant_maintenance(mr, org,
                                       f'Your maintenance request "{mr.title}" could not be actioned. '
                                       f'Reason: {mr.staff_notes or "Contact the agency for details."}')
            messages.warning(request, 'Request rejected.')

        return redirect('finance:maintenance_detail', pk=pk)

    context = {
        'page_title': f'Maintenance — {mr.title}',
        'mr':         mr,
    }
    return render(request, 'finance/maintenance_detail.html', context)


def _notify_tenant_maintenance(mr, org, message):
    tenant_user = getattr(mr.tenant, 'user', None)
    if tenant_user:
        notify(
            recipient=tenant_user,
            message=message,
            url=f'/portal/maintenance/{mr.pk}/',
            level='info',
            notification_type='MAINTENANCE_UPDATE',
            organization=org,
        )


# ─────────────────────────────────────────
# MOVE-OUT REQUESTS — admin views
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_FINANCE)
def moveout_request_list(request):
    from portal.models import MoveOutRequest
    org = request.user.organization
    status = request.GET.get('status', '')

    qs = MoveOutRequest.objects.filter(
        organization=org
    ).select_related(
        'tenant', 'tenancy', 'tenancy__unit', 'tenancy__unit__prop'
    ).order_by('-created_at')

    if status:
        qs = qs.filter(status=status)

    context = {
        'page_title':      'Move-Out Requests',
        'requests':        qs,
        'status_choices':  MoveOutRequest.Status.choices,
        'selected_status': status,
        'pending_count':   qs.filter(status='PENDING').count(),
        'inspection_count': qs.filter(status='INSPECTION').count(),
    }
    return render(request, 'finance/moveout_request_list.html', context)


@login_required
@require_capability(Cap.VIEW_FINANCE)
def moveout_request_detail(request, pk):
    """
    Full move-out workflow:
    PENDING → send to inspection → tick checklist → APPROVED/REJECTED
    On approval: calculates arrears from day 1, deposit refund, ends tenancy.
    """
    from portal.models import MoveOutRequest
    from tenancies.models import Tenancy
    org = request.user.organization
    mor = get_object_or_404(MoveOutRequest, pk=pk, organization=org)

    if request.method == 'POST':
        action = request.POST.get('action')

        # Step 1: Send to inspection
        if action == 'start_inspection':
            mor.status = MoveOutRequest.Status.INSPECTION
            mor.inspected_by = request.user
            mor.inspected_at = timezone.now()
            mor.save(update_fields=[
                     'status', 'inspected_by', 'inspected_at', 'updated_at'])
            _notify_tenant_moveout(mor, org,
                                   'Your move-out request is now under inspection. '
                                   'An agent will visit the unit to complete the checklist.')
            messages.success(request, 'Move-out sent to inspection.')

        # Step 2: Save checklist items (can be called multiple times)
        elif action == 'save_checklist':
            with transaction.atomic():
                for field, _ in MoveOutRequest.CHECKLIST_FIELDS:
                    val = request.POST.get(field)
                    if val == 'ok':
                        setattr(mor, field, True)
                    elif val == 'issue':
                        setattr(mor, field, False)
                    # leave as None if not submitted
                mor.insp_notes = request.POST.get('insp_notes', mor.insp_notes)
                mor.save()
            _notify_tenant_moveout(mor, org,
                                   f'Inspection checklist updated — '
                                   f'{mor.checklist_progress[0]}/{mor.checklist_progress[1]} '
                                   f'items completed.')
            messages.success(request, 'Checklist saved.')

        # Step 3: Approve (checklist must be complete)
        elif action == 'approve':
            if not mor.checklist_complete:
                messages.error(
                    request, 'Complete all checklist items before approving.')
                return redirect('finance:moveout_request_detail', pk=pk)

            damage_deductions = Decimal(
                request.POST.get('damage_deductions', '0') or '0')
            mor.damage_deductions = damage_deductions
            mor.save(update_fields=['damage_deductions'])

            with transaction.atomic():
                # Calculate arrears + deposit refund
                mor.calculate_deposit_refund()

                # End the tenancy
                tenancy = mor.tenancy
                tenancy.status = Tenancy.Status.ENDED
                tenancy.end_date = mor.requested_moveout_date
                tenancy.save(update_fields=['status', 'end_date'])

                # Free the unit
                unit = tenancy.unit
                unit.status = unit.Status.VACANT
                unit.save(update_fields=['status'])

                # Final approval
                mor.status = MoveOutRequest.Status.APPROVED
                mor.reviewed_by = request.user
                mor.reviewed_at = timezone.now()
                mor.save(update_fields=[
                         'status', 'reviewed_by', 'reviewed_at', 'updated_at'])

            _notify_tenant_moveout(mor, org,
                                   f'Your move-out has been approved. '
                                   f'Deposit refund: KSh {mor.deposit_refundable:,.0f}. '
                                   f'Outstanding arrears deducted: KSh {mor.outstanding_arrears:,.0f}.')
            messages.success(
                request,
                f'Move-out approved. Deposit refund: KSh {mor.deposit_refundable:,.0f}.'
            )
            return redirect('finance:moveout_request_list')

        # Reject
        elif action == 'reject':
            mor.status = MoveOutRequest.Status.REJECTED
            mor.rejection_note = request.POST.get('rejection_note', '').strip()
            mor.reviewed_by = request.user
            mor.reviewed_at = timezone.now()
            mor.save(update_fields=[
                'status', 'rejection_note', 'reviewed_by', 'reviewed_at', 'updated_at'])
            _notify_tenant_moveout(mor, org,
                                   f'Your move-out request was rejected. '
                                   f'Reason: {mor.rejection_note or "Contact the agency."}')
            messages.warning(request, 'Move-out request rejected.')
            return redirect('finance:moveout_request_list')

        return redirect('finance:moveout_request_detail', pk=pk)

    context = {
        'page_title':      f'Move-Out — {mor.tenant.full_name}',
        'mor':             mor,
        'checklist_items': mor.checklist_items,
        'progress':        mor.checklist_progress,
        'step':            mor.get_status_step(),
    }
    return render(request, 'finance/moveout_request_detail.html', context)


def _notify_tenant_moveout(mor, org, message):
    tenant_user = getattr(mor.tenant, 'user', None)
    if tenant_user:
        notify(
            recipient=tenant_user,
            message=message,
            url=f'/portal/moveout/{mor.pk}/',
            level='info',
            notification_type='MOVEOUT_UPDATE',
            organization=org,
        )


# ─────────────────────────────────────────
# TRANSFER REQUESTS — admin views
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_FINANCE)
def transfer_request_list(request):
    from portal.models import TransferRequest
    org = request.user.organization
    status = request.GET.get('status', '')

    qs = TransferRequest.objects.filter(
        organization=org
    ).select_related(
        'tenant', 'tenancy', 'tenancy__unit',
        'requested_unit', 'tenancy__unit__prop',
    ).order_by('-created_at')

    if status:
        qs = qs.filter(status=status)

    context = {
        'page_title':      'Transfer Requests',
        'requests':        qs,
        'status_choices':  TransferRequest.Status.choices,
        'selected_status': status,
        'pending_count':   qs.filter(status='PENDING').count(),
    }
    return render(request, 'finance/transfer_request_list.html', context)


@login_required
@require_capability(Cap.MANAGE_FINANCE)
def transfer_request_detail(request, pk):
    """
    Approve: closes old tenancy end-of-month, opens new tenancy,
    carries deposit (top-up charge or credit), transfers arrears.
    Reject: notifies tenant, leaves tenancy unchanged.
    """
    from portal.models import TransferRequest
    from tenancies.models import Tenancy, Transfer
    from finance.models import (
        DepositAccount, DepositMovement, Charge
    )
    org = request.user.organization
    tr = get_object_or_404(TransferRequest, pk=pk, organization=org,
                           status='PENDING')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'approve':
            with transaction.atomic():
                old_tenancy = tr.tenancy
                old_unit = old_tenancy.unit
                new_unit = tr.requested_unit
                effective_date = tr.effective_date or tr.requested_date

                # 1. End old tenancy
                old_tenancy.status = Tenancy.Status.TRANSFERRED
                old_tenancy.end_date = effective_date
                old_tenancy.save(update_fields=['status', 'end_date'])

                # 2. Free old unit
                old_unit.status = old_unit.Status.VACANT
                old_unit.save(update_fields=['status'])

                # 3. Create new tenancy (starts day after effective_date)
                from dateutil.relativedelta import relativedelta
                new_start = effective_date + relativedelta(days=1)
                new_tenancy = Tenancy.objects.create(
                    organization=org,
                    tenant=tr.tenant,
                    unit=new_unit,
                    start_date=new_start,
                    monthly_rent=new_unit.rent_amount,
                    required_deposit=new_unit.deposit_amount,
                    billing_day=old_tenancy.billing_day,
                    status=Tenancy.Status.ACTIVE,
                    created_by=request.user,
                )

                # 4. Occupy new unit
                new_unit.status = new_unit.Status.OCCUPIED
                new_unit.save(update_fields=['status'])

                # 5. Carry deposit
                old_deposit = tr.old_deposit
                new_deposit = tr.new_deposit
                diff = tr.deposit_difference  # positive = tenant owes

                try:
                    old_da = old_tenancy.deposit_account
                    old_balance = old_da.balance
                except Exception:
                    old_balance = Decimal('0')

                new_da = DepositAccount.objects.create(
                    organization=org,
                    tenancy=new_tenancy,
                    required_amount=new_unit.deposit_amount,
                )
                # Transfer existing deposit balance
                if old_balance > 0:
                    DepositMovement.objects.create(
                        deposit_account=new_da,
                        movement_type=DepositMovement.Type.TRANSFER_IN,
                        amount=old_balance,
                        reason=f'Transferred from unit {old_unit.unit_number}',
                        created_by=request.user,
                    )
                    # Debit old account
                    DepositMovement.objects.create(
                        deposit_account=old_da,
                        movement_type=DepositMovement.Type.TRANSFER_OUT,
                        amount=-old_balance,
                        reason=f'Transferred to unit {new_unit.unit_number}',
                        created_by=request.user,
                    )

                # If tenant owes top-up, create a deposit charge on new tenancy
                if diff > 0:
                    Charge.objects.create(
                        organization=org,
                        tenancy=new_tenancy,
                        charge_type=Charge.Type.DEPOSIT,
                        description=f'Deposit top-up — transfer to {new_unit.unit_number}',
                        amount=diff,
                        due_date=new_start,
                        is_deposit_charge=True,
                    )

                # 6. Create immutable Transfer record
                Transfer.objects.create(
                    organization=org,
                    old_tenancy=old_tenancy,
                    new_tenancy=new_tenancy,
                    tenant=tr.tenant,
                    transfer_date=effective_date,
                    old_monthly_rent=old_tenancy.monthly_rent,
                    new_monthly_rent=new_unit.rent_amount,
                    old_deposit_held=old_balance,
                    new_deposit_required=new_unit.deposit_amount,
                    deposit_difference=diff,
                    deposit_disposition=(
                        Transfer.DepositDisposition.TOPUP if diff > 0
                        else Transfer.DepositDisposition.HOLD if diff == 0
                        else Transfer.DepositDisposition.REFUND
                    ),
                    created_by=request.user,
                )

                # 7. Approve the request
                tr.status = TransferRequest.Status.APPROVED
                tr.reviewed_by = request.user
                tr.reviewed_at = timezone.now()
                tr.save(update_fields=[
                        'status', 'reviewed_by', 'reviewed_at', 'updated_at'])

            tenant_user = getattr(tr.tenant, 'user', None)
            if tenant_user:
                msg = (
                    f'Your transfer to unit {new_unit.unit_number} has been approved. '
                    f'Your new tenancy starts {new_start.strftime("%d %b %Y")}.'
                )
                if diff > 0:
                    msg += f' A deposit top-up of KSh {diff:,.0f} is required.'
                notify(
                    recipient=tenant_user, message=msg,
                    url='/portal/transfer/',
                    level='success',
                    notification_type='TRANSFER_UPDATE',
                    organization=org,
                )

            messages.success(
                request,
                f'Transfer approved. New tenancy starts {new_start.strftime("%d %b %Y")}.'
            )
            return redirect('finance:transfer_request_list')

        elif action == 'reject':
            tr.status = TransferRequest.Status.REJECTED
            tr.rejection_note = request.POST.get('rejection_note', '').strip()
            tr.reviewed_by = request.user
            tr.reviewed_at = timezone.now()
            tr.save(update_fields=[
                'status', 'rejection_note', 'reviewed_by', 'reviewed_at', 'updated_at'])

            tenant_user = getattr(tr.tenant, 'user', None)
            if tenant_user:
                notify(
                    recipient=tenant_user,
                    message=(
                        f'Your transfer request to unit {tr.requested_unit.unit_number} '
                        f'was rejected. Reason: {tr.rejection_note or "Contact agency."}'
                    ),
                    url='/portal/transfer/',
                    level='danger',
                    notification_type='TRANSFER_UPDATE',
                    organization=org,
                )
            messages.warning(request, 'Transfer request rejected.')
            return redirect('finance:transfer_request_list')

    context = {
        'page_title': (
            f'Transfer — {tr.tenant.full_name}: '
            f'{tr.tenancy.unit.unit_number} → {tr.requested_unit.unit_number}'
        ),
        'tr': tr,
    }
    return render(request, 'finance/transfer_request_detail.html', context)


# ─────────────────────────────────────────
# VACANCY MANAGEMENT
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_FINANCE)
def vacancy_list(request):
    org = request.user.organization
    prop = request.GET.get('property', '')

    units = Unit.objects.filter(
        prop__organization=org,
        status=Unit.Status.VACANT,
        is_archived=False,
    ).select_related('prop', 'house_type').order_by('prop', 'unit_number')

    if prop:
        units = units.filter(prop__id=prop)

    # Calculate days vacant for each unit
    today = timezone.now().date()
    unit_data = []
    for unit in units:
        # Find last tenancy end date
        last_tenancy = unit.tenancies.filter(
            status__in=['ENDED', 'TERMINATED', 'TRANSFERRED']
        ).order_by('-end_date').first()
        days_vacant = (
            today - last_tenancy.end_date).days if last_tenancy else None

        unit_data.append({
            'unit':         unit,
            'days_vacant':  days_vacant,
            'last_tenant':  last_tenancy.tenant.full_name if last_tenancy else '—',
            'vacated_date': last_tenancy.end_date if last_tenancy else None,
        })

    # Sort longest vacant first
    unit_data.sort(
        key=lambda x: x['days_vacant'] if x['days_vacant'] is not None else -1,
        reverse=True
    )

    context = {
        'page_title': 'Vacant Units',
        'unit_data':  unit_data,
        'total':      len(unit_data),
        'properties': Property.objects.filter(
            organization=org).exclude(status='ARCHIVED'),
        'selected_property': prop,
        'potential_rent':    sum(u['unit'].rent_amount for u in unit_data),
    }
    return render(request, 'finance/vacancy_list.html', context)


# ─────────────────────────────────────────
# ENHANCED DASHBOARD KPIs  (replaces core/views.py dashboard)
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_FINANCE)
def admin_dashboard_kpis(request):
    """
    AJAX endpoint — returns live KPI data as JSON.
    Called by the dashboard page every 60s to refresh counters.
    """
    from django.http import JsonResponse
    from portal.models import MaintenanceRequest, MoveOutRequest, TransferRequest
    org = request.user.organization

    units = Unit.objects.filter(prop__organization=org, is_archived=False)
    total = units.count()

    pending_notices = RentNotice.objects.filter(
        organization=org, status='SUBMITTED').count()
    open_maintenance = MaintenanceRequest.objects.filter(
        organization=org,
        status__in=['PENDING', 'ASSIGNED', 'IN_PROGRESS']).count()
    pending_moveouts = MoveOutRequest.objects.filter(
        organization=org,
        status__in=['PENDING', 'INSPECTION']).count()
    pending_transfers = TransferRequest.objects.filter(
        organization=org, status='PENDING').count()

    return JsonResponse({
        'vacant':             units.filter(status='VACANT').count(),
        'occupied':           units.filter(status='OCCUPIED').count(),
        'maintenance_units':  units.filter(status='MAINTENANCE').count(),
        'total_units':        total,
        'pending_notices':    pending_notices,
        'open_maintenance':   open_maintenance,
        'pending_moveouts':   pending_moveouts,
        'pending_transfers':  pending_transfers,
        'action_items':       pending_notices + open_maintenance + pending_moveouts + pending_transfers,
    })
