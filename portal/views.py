from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone

from .decorators import tenant_required
from .services import get_tenant_summary, get_tenant_statement
from finance.models import Payment, DepositAccount
from receipts.models import Receipt


# ─────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────

@tenant_required
def portal_dashboard(request):
    tenant = request.user.tenant_profile
    summary = get_tenant_summary(tenant)

    context = {
        'page_title': 'My Account',
        'tenant':     tenant,
        'summary':    summary,
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

@tenant_required
def portal_payments(request):
    tenant = request.user.tenant_profile
    tenancy = tenant.get_active_tenancy()

    payments = Payment.objects.filter(
        tenant=tenant,
        status='VERIFIED'
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
    tenant = request.user.tenant_profile

    receipt = get_object_or_404(
        Receipt,
        pk=pk,
        payment__tenant=tenant  # enforce tenant owns this receipt
    )

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
    Generates a tenant-safe PDF receipt.
    Never exposes M-Pesa transaction code or internal IDs.
    """
    from django.template.loader import render_to_string
    import weasyprint

    tenant = request.user.tenant_profile
    receipt = get_object_or_404(
        Receipt,
        pk=pk,
        payment__tenant=tenant
    )

    html_string = render_to_string('portal/receipt_pdf.html', {
        'receipt':      receipt,
        'payment':      receipt.payment,
        'tenant':       tenant,
        'organization': request.user.organization,
        'now':          timezone.now(),
    })

    pdf = weasyprint.HTML(string=html_string).write_pdf()

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
