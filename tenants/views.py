from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from accounts.permissions import require_capability, Cap
from .models import Tenant
from .forms import TenantForm


@login_required
@require_capability(Cap.VIEW_TENANTS)
def tenant_list(request):
    organization = request.user.organization
    query = request.GET.get('q', '')
    status = request.GET.get('status', '')

    tenants = Tenant.objects.filter(organization=organization)

    if query:
        tenants = tenants.filter(
            Q(full_name__icontains=query) |
            Q(tenant_number__icontains=query) |
            Q(phone__icontains=query) |
            Q(email__icontains=query)
        )

    if status:
        tenants = tenants.filter(status=status)

    tenants = tenants.order_by('full_name')

    # Attach current unit to each row
    for tenant in tenants:
        tenant.current_unit = tenant.get_current_unit()

    context = {
        'page_title':      'Tenants',
        'tenants':         tenants,
        'query':           query,
        'selected_status': status,
        'status_choices':  Tenant.Status.choices,
        'total':           tenants.count(),
    }
    return render(request, 'tenants/tenant_list.html', context)


@login_required
@require_capability(Cap.VIEW_TENANTS)
def tenant_detail(request, pk):
    organization = request.user.organization
    tenant = get_object_or_404(Tenant, pk=pk, organization=organization)

    tenancies = tenant.tenancies.select_related(
        'unit', 'unit__prop'
    ).order_by('-start_date')

    context = {
        'page_title':     tenant.full_name,
        'tenant':         tenant,
        'tenancies':      tenancies,
        'active_tenancy': tenant.get_active_tenancy(),
        'current_unit':   tenant.get_current_unit(),
        'current_property': tenant.get_current_property(),
    }
    return render(request, 'tenants/tenant_detail.html', context)


@login_required
@require_capability(Cap.MANAGE_TENANTS)
def tenant_create(request):
    organization = request.user.organization

    if request.method == 'POST':
        form = TenantForm(request.POST)
        if form.is_valid():
            tenant = form.save(commit=False)
            tenant.organization = organization
            tenant.save()
            messages.success(
                request, f'Tenant "{tenant.full_name}" created successfully.')
            return redirect('tenants:detail', pk=tenant.pk)
    else:
        form = TenantForm()

    context = {
        'page_title': 'Add Tenant',
        'form':       form,
        'action':     'Create Tenant',
    }
    return render(request, 'tenants/tenant_form.html', context)


@login_required
@require_capability(Cap.MANAGE_TENANTS)
def tenant_edit(request, pk):
    organization = request.user.organization
    tenant = get_object_or_404(Tenant, pk=pk, organization=organization)

    if request.method == 'POST':
        form = TenantForm(request.POST, instance=tenant)
        if form.is_valid():
            form.save()
            messages.success(
                request, f'Tenant "{tenant.full_name}" updated successfully.')
            return redirect('tenants:detail', pk=tenant.pk)
    else:
        form = TenantForm(instance=tenant)

    context = {
        'page_title': f'Edit {tenant.full_name}',
        'form':       form,
        'tenant':     tenant,
        'action':     'Save Changes',
    }
    return render(request, 'tenants/tenant_form.html', context)
