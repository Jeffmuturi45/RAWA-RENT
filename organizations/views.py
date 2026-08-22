from datetime import date
from decimal import Decimal

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from accounts.permissions import require_capability, Cap
from audit.services import log_action, Action, get_client_ip

from .forms import AgencyProfileForm, BrandingForm, SystemSettingsForm, THEME_FIELDS


# Which form handles each tab of the settings page.
SECTION_FORMS = {
    'agency':   AgencyProfileForm,
    'branding': BrandingForm,
    'system':   SystemSettingsForm,
}


def _snapshot(org, fields):
    """Plain-value snapshot of the given fields, for the audit before/after."""
    snap = {}
    for f in fields:
        value = getattr(org, f, None)
        snap[f] = str(value) if value is not None else None
    return snap


@login_required
@require_capability(Cap.MANAGE_SETTINGS)
def settings_home(request):
    org = request.user.organization
    if org is None:
        messages.error(request, 'Your account is not linked to an agency.')
        return redirect('core:dashboard')

    active = request.POST.get('section') or request.GET.get('tab') or 'agency'
    if active not in SECTION_FORMS:
        active = 'agency'

    forms = {}
    for name, form_class in SECTION_FORMS.items():
        if request.method == 'POST' and name == active:
            form_class_fields = list(form_class.Meta.fields)
            before = _snapshot(org, form_class_fields)
            form = form_class(request.POST, request.FILES, instance=org)
            if form.is_valid():
                form.save()
                org.refresh_from_db()
                log_action(
                    Action.SETTINGS_UPDATED, actor=request.user,
                    organization=org, obj=org,
                    before=before, after=_snapshot(org, form_class_fields),
                    reason=f'Settings section: {name}',
                    ip=get_client_ip(request),
                )
                messages.success(request, 'Settings saved.')
                return redirect(f"{request.path}?tab={name}")
            forms[name] = form
        else:
            forms[name] = form_class(instance=org)

    context = {
        'page_title':   'Settings',
        'org':          org,
        'agency_form':   forms['agency'],
        'branding_form': forms['branding'],
        'system_form':   forms['system'],
        'active_tab':    active,
        'theme_fields': [forms['branding'][f] for f in THEME_FIELDS],
    }
    return render(request, 'organizations/settings.html', context)


@login_required
@require_capability(Cap.MANAGE_SETTINGS)
def receipt_preview(request):
    """
    Live sample receipt using the agency's current branding (spec §25),
    so the owner can see the effect before printing anything real.
    """
    org = request.user.organization
    sample = {
        'receipt_number': 'REC-2026-000421',
        'tenant_name':    'John Mwangi',
        'property_name':  'Anju Apartments',
        'unit_number':    'A101',
        'issued_at':      date.today(),
        'description':    'August Rent',
        'amount':         Decimal('8000'),
        'method':         'M-Pesa',
    }
    return render(request, 'organizations/receipt_preview.html', {
        'page_title': 'Receipt Preview',
        'org':        org,
        'sample':     sample,
    })
