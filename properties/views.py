from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from accounts.permissions import require_capability, Cap
from .models import Property, HouseType, Unit
from .forms import PropertyForm, HouseTypeForm, UnitForm


# ─────────────────────────────────────────
# PROPERTIES
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_PROPERTIES)
def property_list(request):
    organization = request.user.organization
    query = request.GET.get('q', '')

    properties = Property.objects.filter(
        organization=organization
    ).exclude(status='ARCHIVED')

    if query:
        properties = properties.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(city__icontains=query)
        )

    for prop in properties:
        prop.unit_count = prop.units.filter(is_archived=False).count()
        prop.occupied_count = prop.get_occupied_units()
        prop.vacant_count = prop.get_vacant_units()
        prop.occupancy = prop.get_occupancy_rate()

    context = {
        'page_title':   'Properties',
        'properties':   properties,
        'query':        query,
        'total':        properties.count(),
    }
    return render(request, 'properties/property_list.html', context)


@login_required
@require_capability(Cap.VIEW_PROPERTIES)
def property_detail(request, pk):
    organization = request.user.organization
    prop = get_object_or_404(Property, pk=pk, organization=organization)

    units = prop.units.filter(is_archived=False).select_related(
        'house_type'
    ).order_by('unit_number')

    house_types = prop.house_types.all()

    # Attach tenancy info to each unit
    for unit in units:
        unit.tenancy = unit.get_active_tenancy()
        unit.tenant = unit.get_current_tenant()

    context = {
        'page_title':   prop.name,
        'prop':         prop,
        'units':        units,
        'house_types':  house_types,
        'total_units':  units.count(),
        'occupied':     prop.get_occupied_units(),
        'vacant':       prop.get_vacant_units(),
        'maintenance':  prop.get_maintenance_units(),
        'occupancy':    prop.get_occupancy_rate(),
        'finance':      _property_finance(organization, prop),
    }
    return render(request, 'properties/property_detail.html', context)


def _property_finance(organization, prop):
    """Collection stats for a property (spec §34). Imported lazily to keep
    the properties app decoupled from finance at import time."""
    from finance.services import arrears_service
    return arrears_service.collection_stats(organization, prop=prop)


@login_required
@require_capability(Cap.MANAGE_PROPERTIES)
def property_create(request):
    organization = request.user.organization

    if request.method == 'POST':
        form = PropertyForm(request.POST, request.FILES)
        if form.is_valid():
            prop = form.save(commit=False)
            prop.organization = organization
            prop.save()
            messages.success(
                request, f'Property "{prop.name}" created successfully.')
            return redirect('properties:detail', pk=prop.pk)
    else:
        form = PropertyForm()

    context = {
        'page_title': 'Add Property',
        'form':       form,
        'action':     'Create',
    }
    return render(request, 'properties/property_form.html', context)


@login_required
@require_capability(Cap.MANAGE_PROPERTIES)
def property_edit(request, pk):
    organization = request.user.organization
    prop = get_object_or_404(Property, pk=pk, organization=organization)

    if request.method == 'POST':
        form = PropertyForm(request.POST, request.FILES, instance=prop)
        if form.is_valid():
            form.save()
            messages.success(
                request, f'Property "{prop.name}" updated successfully.')
            return redirect('properties:detail', pk=prop.pk)
    else:
        form = PropertyForm(instance=prop)

    context = {
        'page_title': f'Edit {prop.name}',
        'form':       form,
        'prop':       prop,
        'action':     'Save Changes',
    }
    return render(request, 'properties/property_form.html', context)


# ─────────────────────────────────────────
# HOUSE TYPES
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.MANAGE_PROPERTIES)
def house_type_create(request, property_pk):
    organization = request.user.organization
    prop = get_object_or_404(Property, pk=property_pk,
                             organization=organization)

    if request.method == 'POST':
        form = HouseTypeForm(request.POST)
        if form.is_valid():
            ht = form.save(commit=False)
            ht.prop = prop
            ht.save()
            messages.success(request, f'House type "{ht.name}" added.')
            return redirect('properties:detail', pk=prop.pk)
    else:
        form = HouseTypeForm()

    context = {
        'page_title': f'Add House Type — {prop.name}',
        'form':       form,
        'prop':       prop,
        'action':     'Add House Type',
    }
    return render(request, 'properties/house_type_form.html', context)


@login_required
@require_capability(Cap.MANAGE_PROPERTIES)
def house_type_edit(request, pk):
    organization = request.user.organization
    ht = get_object_or_404(HouseType, pk=pk, prop__organization=organization)

    if request.method == 'POST':
        form = HouseTypeForm(request.POST, instance=ht)
        if form.is_valid():
            form.save()
            messages.success(request, f'House type "{ht.name}" updated.')
            return redirect('properties:detail', pk=ht.prop.pk)
    else:
        form = HouseTypeForm(instance=ht)

    context = {
        'page_title': f'Edit {ht.name}',
        'form':       form,
        'ht':         ht,
        'prop':       ht.prop,
        'action':     'Save Changes',
    }
    return render(request, 'properties/house_type_form.html', context)


# ─────────────────────────────────────────
# UNITS
# ─────────────────────────────────────────

@login_required
@require_capability(Cap.VIEW_PROPERTIES)
def unit_list(request):
    organization = request.user.organization
    query = request.GET.get('q', '')
    status = request.GET.get('status', '')
    property_id = request.GET.get('property', '')

    units = Unit.objects.filter(
        prop__organization=organization,
        is_archived=False
    ).select_related('prop', 'house_type')

    if query:
        units = units.filter(
            Q(unit_number__icontains=query) |
            Q(prop__name__icontains=query)
        )

    if status:
        units = units.filter(status=status)

    if property_id:
        units = units.filter(prop_id=property_id)

    units = units.order_by('prop__name', 'unit_number')

    # Attach current tenant to each row
    for unit in units:
        unit.tenant = unit.get_current_tenant()

    properties = Property.objects.filter(
        organization=organization
    ).exclude(status='ARCHIVED').order_by('name')

    context = {
        'page_title':      'Units',
        'units':           units,
        'query':           query,
        'selected_status': status,
        'selected_property': property_id,
        'properties':      properties,
        'status_choices':  Unit.Status.choices,
        'total':           units.count(),
    }
    return render(request, 'properties/unit_list.html', context)


@login_required
@require_capability(Cap.MANAGE_PROPERTIES)
def unit_create(request, property_pk):
    organization = request.user.organization
    prop = get_object_or_404(Property, pk=property_pk,
                             organization=organization)

    if request.method == 'POST':
        form = UnitForm(request.POST, prop=prop)
        if form.is_valid():
            unit = form.save(commit=False)
            unit.prop = prop
            unit.save()
            messages.success(request, f'Unit "{unit.unit_number}" created.')
            return redirect('properties:detail', pk=prop.pk)
    else:
        form = UnitForm(prop=prop)

    context = {
        'page_title': f'Add Unit — {prop.name}',
        'form':       form,
        'prop':       prop,
        'action':     'Create Unit',
    }
    return render(request, 'properties/unit_form.html', context)


@login_required
@require_capability(Cap.VIEW_PROPERTIES)
def unit_detail(request, pk):
    organization = request.user.organization
    unit = get_object_or_404(Unit, pk=pk, prop__organization=organization)

    tenancies = unit.tenancies.select_related(
        'tenant'
    ).order_by('-start_date')

    context = {
        'page_title': f'Unit {unit.unit_number}',
        'unit':       unit,
        'prop':       unit.prop,
        'tenancies':  tenancies,
        'active_tenancy': unit.get_active_tenancy(),
    }
    return render(request, 'properties/unit_detail.html', context)


@login_required
@require_capability(Cap.MANAGE_PROPERTIES)
def unit_edit(request, pk):
    organization = request.user.organization
    unit = get_object_or_404(Unit, pk=pk, prop__organization=organization)

    if request.method == 'POST':
        form = UnitForm(request.POST, instance=unit, prop=unit.prop)
        if form.is_valid():
            form.save()
            messages.success(request, f'Unit "{unit.unit_number}" updated.')
            return redirect('properties:unit_detail', pk=unit.pk)
    else:
        form = UnitForm(instance=unit, prop=unit.prop)

    context = {
        'page_title': f'Edit Unit {unit.unit_number}',
        'form':       form,
        'unit':       unit,
        'prop':       unit.prop,
        'action':     'Save Changes',
    }
    return render(request, 'properties/unit_form.html', context)
