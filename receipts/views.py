from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages

from accounts.permissions import require_capability, Cap
from audit.services import get_client_ip
from finance.models import Payment

from .models import Receipt
from .services import (
    generate_receipt, receipt_context, render_pdf,
    weasyprint_available, ReceiptNotAllowed,
)


@login_required
@require_capability(Cap.VIEW_FINANCE)
def receipt_list(request):
    org = request.user.organization
    receipts = Receipt.objects.filter(organization=org).select_related(
        'payment', 'payment__tenant', 'payment__tenancy',
        'payment__tenancy__unit', 'payment__tenancy__unit__prop')

    context = {
        'page_title': 'Receipts',
        'receipts':   receipts,
        'total':      receipts.count(),
        'pdf_available': weasyprint_available(),
    }
    return render(request, 'receipts/receipt_list.html', context)


@login_required
@require_capability(Cap.VIEW_FINANCE)
def receipt_issue(request, payment_pk):
    """Issue (or fetch) the receipt for a verified payment, then show it."""
    org = request.user.organization
    payment = get_object_or_404(Payment, pk=payment_pk, organization=org)

    try:
        receipt = generate_receipt(payment, actor=request.user,
                                  ip=get_client_ip(request))
    except ReceiptNotAllowed as e:
        messages.error(request, str(e))
        return redirect('finance:payment_detail', pk=payment.pk)

    return redirect('receipts:detail', pk=receipt.pk)


@login_required
@require_capability(Cap.VIEW_FINANCE)
def receipt_detail(request, pk):
    """Print-ready HTML receipt (org-scoped; UUID URL — spec §41)."""
    org = request.user.organization
    receipt = get_object_or_404(
        Receipt.objects.select_related(
            'organization', 'payment', 'payment__tenant', 'payment__tenancy',
            'payment__tenancy__unit', 'payment__tenancy__unit__prop'),
        pk=pk, organization=org)

    return render(request, 'receipts/receipt_print.html', {
        'page_title':    receipt.receipt_number,
        'org':           receipt.organization,
        'r':             receipt_context(receipt),
        'receipt':       receipt,
        'pdf_available': weasyprint_available(),
    })


@login_required
@require_capability(Cap.VIEW_FINANCE)
def receipt_pdf(request, pk):
    """
    PDF receipt. If WeasyPrint's native libraries are unavailable, fall back
    to the print-ready HTML view instead of failing.
    """
    org = request.user.organization
    receipt = get_object_or_404(Receipt, pk=pk, organization=org)

    pdf = render_pdf(receipt)
    if pdf is None:
        messages.info(
            request,
            'PDF export is unavailable on this server — use your browser\'s '
            'Print dialog (or Save as PDF) on this receipt.')
        return redirect('receipts:detail', pk=receipt.pk)

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="{receipt.receipt_number}.pdf"')
    return response
