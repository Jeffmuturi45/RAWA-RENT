from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.urls import reverse

from accounts.permissions import require_capability, Cap
from audit.services import get_client_ip
from notifications.models import Notification, notify_org_admins
from properties.models import Unit
from finance.services.transfer_service import (
    calculate_transfer_summary, execute_transfer, TransferError
)
from finance.services.moveout_service import (
    calculate_moveout_summary, execute_moveout, MoveOutError
)
from .models import Tenancy, Transfer, MoveOut
from .forms import TenancyForm, TransferInitiateForm, TransferConfirmForm, MoveOutForm


# ─────────────────────────────────────────
# LIST
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_TENANTS)
def tenancy_list(request):
    organization = request.user.organization
    query = request.GET.get('q', '')
    status = request.GET.get('status', '')

    tenancies = Tenancy.objects.filter(
        organization=organization
    ).select_related('tenant', 'unit', 'unit__prop')

    if query:
        tenancies = tenancies.filter(
            Q(tenant__full_name__icontains=query) |
            Q(tenant__tenant_number__icontains=query) |
            Q(unit__unit_number__icontains=query)
        )
    if status:
        tenancies = tenancies.filter(status=status)

    tenancies = tenancies.order_by('-start_date')

    context = {
        'page_title':      'Tenancies',
        'tenancies':       tenancies,
        'query':           query,
        'selected_status': status,
        'status_choices':  Tenancy.Status.choices,
        'total':           tenancies.count(),
    }
    return render(request, 'tenancies/tenancy_list.html', context)


# ─────────────────────────────────────────
# CREATE
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.MANAGE_TENANTS)
def tenancy_create(request):
    organization = request.user.organization

    if request.method == 'POST':
        form = TenancyForm(request.POST, org=organization)
        if form.is_valid():
            tenancy = form.save(commit=False)
            tenancy.organization = organization
            tenancy.created_by = request.user
            tenancy.save()

            unit = tenancy.unit
            unit.status = Unit.Status.OCCUPIED
            unit.save(update_fields=['status', 'updated_at'])

            notify_org_admins(
                organization,
                f'{tenancy.tenant.full_name} placed in '
                f'{unit.prop.name} · Unit {unit.unit_number}.',
                url=reverse('tenancies:detail', args=[tenancy.pk]),
                level=Notification.Level.SUCCESS,
                actor=request.user,
            )
            messages.success(
                request,
                f'{tenancy.tenant.full_name} placed in '
                f'{unit.prop.name} · Unit {unit.unit_number}.'
            )
            return redirect('tenants:detail', pk=tenancy.tenant.pk)
    else:
        initial = {}
        tenant_id = request.GET.get('tenant')
        if tenant_id:
            initial['tenant'] = tenant_id

        unit_id = request.GET.get('unit')
        if unit_id:
            unit = Unit.objects.filter(
                pk=unit_id, prop__organization=organization
            ).first()
            if unit:
                initial['unit'] = unit.pk
                initial['monthly_rent'] = unit.rent_amount
                initial['required_deposit'] = unit.deposit_amount

        form = TenancyForm(org=organization, initial=initial)

    context = {
        'page_title': 'Place Tenant in Unit',
        'form':       form,
        'action':     'Create Tenancy',
    }
    return render(request, 'tenancies/tenancy_form.html', context)


# ─────────────────────────────────────────
# DETAIL
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_TENANTS)
def tenancy_detail(request, pk):
    organization = request.user.organization
    tenancy = get_object_or_404(
        Tenancy.objects.select_related('tenant', 'unit', 'unit__prop'),
        pk=pk, organization=organization
    )
    rent_variations = tenancy.rent_variations.order_by('-effective_date')

    # Check for linked transfer/moveout records
    transfer_out = getattr(tenancy, 'transfer_out', None)
    transfer_in = getattr(tenancy, 'transfer_in', None)
    moveout = getattr(tenancy, 'moveout', None)

    context = {
        'page_title':      f'Tenancy — {tenancy.tenant.full_name}',
        'tenancy':         tenancy,
        'rent_variations': rent_variations,
        'transfer_out':    transfer_out,
        'transfer_in':     transfer_in,
        'moveout':         moveout,
    }
    return render(request, 'tenancies/tenancy_detail.html', context)


# ─────────────────────────────────────────
# TRANSFER — Step 1: Initiate
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.MANAGE_TENANTS)
def transfer_initiate(request, pk):
    """
    Step 1: Staff selects new unit and transfer date.
    System calculates financial summary and stores in session for step 2.
    """
    organization = request.user.organization
    tenancy = get_object_or_404(
        Tenancy, pk=pk,
        organization=organization,
        status=Tenancy.Status.ACTIVE
    )

    if request.method == 'POST':
        form = TransferInitiateForm(
            request.POST,
            org=organization,
            current_unit=tenancy.unit
        )
        if form.is_valid():
            new_unit = form.cleaned_data['new_unit']
            transfer_date = form.cleaned_data['transfer_date']
            new_monthly_rent = form.cleaned_data['new_monthly_rent']
            new_required_deposit = form.cleaned_data['new_required_deposit']
            reason = form.cleaned_data.get('reason', '')

            summary = calculate_transfer_summary(tenancy, new_unit)

            # Store transfer plan in session
            request.session['transfer_plan'] = {
                'tenancy_pk':          str(tenancy.pk),
                'new_unit_pk':         str(new_unit.pk),
                'transfer_date':       transfer_date.isoformat(),
                'new_monthly_rent':    str(new_monthly_rent),
                'new_required_deposit': str(new_required_deposit),
                'reason':              reason,
                # Financial snapshot for display
                'old_unit_number':     tenancy.unit.unit_number,
                'new_unit_number':     new_unit.unit_number,
                'old_monthly_rent':    str(tenancy.monthly_rent),
                'old_deposit_held':    str(summary['old_deposit_held']),
                'new_deposit_required': str(new_required_deposit),
                'deposit_difference':  str(summary['deposit_difference']),
                'outstanding_rent':    str(summary['outstanding_rent']),
            }
            return redirect('tenancies:transfer_confirm', pk=tenancy.pk)
    else:
        form = TransferInitiateForm(
            org=organization,
            current_unit=tenancy.unit,
            initial={
                'new_monthly_rent':     tenancy.monthly_rent,
                'new_required_deposit': tenancy.required_deposit,
            }
        )

    context = {
        'page_title': f'Transfer — {tenancy.tenant.full_name}',
        'tenancy':    tenancy,
        'form':       form,
    }
    return render(request, 'tenancies/transfer_initiate.html', context)


# ─────────────────────────────────────────
# TRANSFER — Step 2: Confirm
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.MANAGE_TENANTS)
def transfer_confirm(request, pk):
    """
    Step 2: Manager reviews financial summary and confirms transfer.
    Only MANAGER and AGENCY_OWNER can confirm.
    """
    organization = request.user.organization

    # Only managers and owners can confirm transfers
    if request.user.role not in ('MANAGER', 'AGENCY_OWNER'):
        messages.error(request, 'Only managers can confirm transfers.')
        return redirect('tenancies:detail', pk=pk)

    tenancy = get_object_or_404(
        Tenancy, pk=pk,
        organization=organization,
        status=Tenancy.Status.ACTIVE
    )

    plan = request.session.get('transfer_plan')
    if not plan or plan.get('tenancy_pk') != str(tenancy.pk):
        messages.error(
            request, 'Transfer session expired. Please start again.')
        return redirect('tenancies:transfer_initiate', pk=pk)

    new_unit = get_object_or_404(Unit, pk=plan['new_unit_pk'])

    if request.method == 'POST':
        form = TransferConfirmForm(request.POST)
        if form.is_valid():
            try:
                from decimal import Decimal
                from datetime import date

                transfer = execute_transfer(
                    old_tenancy=tenancy,
                    new_unit=new_unit,
                    transfer_date=date.fromisoformat(plan['transfer_date']),
                    new_monthly_rent=Decimal(plan['new_monthly_rent']),
                    new_required_deposit=Decimal(plan['new_required_deposit']),
                    deposit_disposition=form.cleaned_data['deposit_disposition'],
                    reason=plan.get('reason', ''),
                    notes=form.cleaned_data.get('notes', ''),
                    actor=request.user,
                    ip=get_client_ip(request),
                )

                # Clear session
                del request.session['transfer_plan']

                notify_org_admins(
                    organization,
                    f'{tenancy.tenant.full_name} transferred from '
                    f'{plan["old_unit_number"]} to {plan["new_unit_number"]}.',
                    url=reverse('tenancies:detail', args=[
                                transfer.new_tenancy.pk]),
                    level=Notification.Level.SUCCESS,
                    actor=request.user,
                )

                messages.success(
                    request,
                    f'{tenancy.tenant.full_name} successfully transferred to '
                    f'Unit {new_unit.unit_number}.'
                )
                return redirect('tenancies:detail', pk=transfer.new_tenancy.pk)

            except TransferError as e:
                messages.error(request, str(e))
    else:
        # Pre-select disposition based on deposit difference
        diff = Decimal(plan['deposit_difference'])
        if diff > 0:
            initial_disposition = 'TOPUP'
        elif diff < 0:
            initial_disposition = 'HOLD'
        else:
            initial_disposition = 'EXACT'
        form = TransferConfirmForm(
            initial={'deposit_disposition': initial_disposition})

    context = {
        'page_title': f'Confirm Transfer — {tenancy.tenant.full_name}',
        'tenancy':    tenancy,
        'new_unit':   new_unit,
        'plan':       plan,
        'form':       form,
    }
    return render(request, 'tenancies/transfer_confirm.html', context)


# ─────────────────────────────────────────
# MOVE-OUT
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.MANAGE_TENANTS)
def moveout_create(request, pk):
    """
    Formal move-out workflow.
    Only MANAGER and AGENCY_OWNER can execute a move-out.
    """
    organization = request.user.organization

    if request.user.role not in ('MANAGER', 'AGENCY_OWNER'):
        messages.error(request, 'Only managers can process move-outs.')
        return redirect('tenancies:detail', pk=pk)

    tenancy = get_object_or_404(
        Tenancy, pk=pk,
        organization=organization,
        status=Tenancy.Status.ACTIVE
    )

    summary = calculate_moveout_summary(tenancy)

    if request.method == 'POST':
        form = MoveOutForm(request.POST)
        if form.is_valid():
            try:
                moveout = execute_moveout(
                    tenancy=tenancy,
                    notice_date=form.cleaned_data['notice_date'],
                    moveout_date=form.cleaned_data['moveout_date'],
                    keys_returned=form.cleaned_data['keys_returned'],
                    walls_condition=form.cleaned_data['walls_condition'],
                    windows_condition=form.cleaned_data['windows_condition'],
                    plumbing_condition=form.cleaned_data['plumbing_condition'],
                    electrical_condition=form.cleaned_data['electrical_condition'],
                    general_condition=form.cleaned_data['general_condition'],
                    inspection_notes=form.cleaned_data.get(
                        'inspection_notes', ''),
                    damage_deductions=form.cleaned_data['damage_deductions'],
                    deposit_settlement=form.cleaned_data['deposit_settlement'],
                    reason=form.cleaned_data.get('reason', ''),
                    notes=form.cleaned_data.get('notes', ''),
                    actor=request.user,
                    ip=get_client_ip(request),
                )

                notify_org_admins(
                    organization,
                    f'{tenancy.tenant.full_name} has moved out of '
                    f'Unit {tenancy.unit.unit_number}.',
                    level=Notification.Level.INFO,
                    actor=request.user,
                )

                messages.success(
                    request,
                    f'Move-out processed for {tenancy.tenant.full_name}. '
                    f'Unit {tenancy.unit.unit_number} is now vacant.'
                )
                return redirect('tenants:detail', pk=tenancy.tenant.pk)

            except MoveOutError as e:
                messages.error(request, str(e))
    else:
        form = MoveOutForm()

    context = {
        'page_title': f'Move-Out — {tenancy.tenant.full_name}',
        'tenancy':    tenancy,
        'summary':    summary,
        'form':       form,
    }
    return render(request, 'tenancies/moveout_form.html', context)
