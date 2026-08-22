from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.urls import reverse

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
