from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.urls import reverse
from accounts.permissions import require_capability, Cap
from notifications.models import Notification, notify_org_admins
from properties.models import Unit
from .models import Tenancy
from .forms import TenancyForm


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

            # Occupy the unit
            unit = tenancy.unit
            unit.status = Unit.Status.OCCUPIED
            unit.save(update_fields=['status', 'updated_at'])

            # Notify agency owners/managers
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


@login_required
@require_capability(Cap.VIEW_TENANTS)
def tenancy_detail(request, pk):
    organization = request.user.organization
    tenancy = get_object_or_404(
        Tenancy.objects.select_related('tenant', 'unit', 'unit__prop'),
        pk=pk, organization=organization
    )

    rent_variations = tenancy.rent_variations.order_by('-effective_date')

    context = {
        'page_title':      f'Tenancy — {tenancy.tenant.full_name}',
        'tenancy':         tenancy,
        'rent_variations': rent_variations,
    }
    return render(request, 'tenancies/tenancy_detail.html', context)
