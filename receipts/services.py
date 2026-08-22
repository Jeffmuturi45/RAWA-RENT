"""
Receipt issuing and rendering.

PDF generation uses WeasyPrint when its native libraries are available.
On systems without them (common on Windows), render_pdf() returns None and
callers fall back to the print-ready HTML receipt — never a 500.
"""
import logging
import re

from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from audit.services import log_action, Action
from finance.models import Payment
from .models import Receipt

logger = logging.getLogger(__name__)


class ReceiptNotAllowed(Exception):
    """Raised when a receipt is requested for a non-verified payment."""


def weasyprint_available():
    """True if WeasyPrint can actually render (native libs present)."""
    try:
        from weasyprint import HTML  # noqa: F401
    except Exception:
        return False
    return True


def _next_receipt_number(organization, year):
    """
    Next sequential number for the org+year, e.g. REC-2026-000421.
    Callers must hold a transaction; we scan existing numbers for the year.
    """
    prefix = f'REC-{year}-'
    last = (
        Receipt.objects.filter(organization=organization,
                               receipt_number__startswith=prefix)
        .order_by('-receipt_number')
        .values_list('receipt_number', flat=True)
        .first()
    )
    seq = 0
    if last:
        m = re.search(r'(\d+)$', last)
        if m:
            seq = int(m.group(1))
    return f'{prefix}{seq + 1:06d}'


@transaction.atomic
def generate_receipt(payment, actor=None, ip=''):
    """
    Issue a receipt for a VERIFIED payment. Idempotent — returns the existing
    receipt if one was already issued.
    """
    existing = Receipt.objects.filter(payment=payment).first()
    if existing:
        return existing

    if payment.status != Payment.Status.VERIFIED:
        raise ReceiptNotAllowed(
            'A receipt can only be issued for a verified payment.')

    # Lock the payment row to serialise concurrent issue attempts.
    Payment.objects.select_for_update().get(pk=payment.pk)

    year = (payment.payment_date or timezone.now().date()).year
    receipt = Receipt.objects.create(
        organization=payment.organization,
        payment=payment,
        receipt_number=_next_receipt_number(payment.organization, year),
        issued_by=actor,
    )

    log_action(
        Action.RECEIPT_ISSUED, actor=actor, organization=payment.organization,
        obj=receipt, after={'receipt_number': receipt.receipt_number,
                            'amount': str(payment.amount)},
        ip=ip,
    )
    return receipt


def receipt_context(receipt):
    """
    Build the whitelisted render context. Only tenant-facing fields are
    included — no M-Pesa code, no UUIDs, no staff identifiers (§24).
    """
    payment = receipt.payment
    tenancy = payment.tenancy

    allocations = list(payment.allocations.select_related('charge'))
    if allocations:
        description = ', '.join(
            a.charge.description or a.charge.get_charge_type_display()
            for a in allocations[:3]
        )
        if len(allocations) > 3:
            description += ', …'
    elif payment.deposit_allocated:
        description = 'Deposit'
    else:
        description = 'Payment on account'

    return {
        'receipt_number': receipt.receipt_number,
        'tenant_name':    payment.tenant.full_name,
        'property_name':  tenancy.unit.prop.name if tenancy else '—',
        'unit_number':    tenancy.unit.unit_number if tenancy else '—',
        'issued_at':      payment.payment_date,
        'description':    description,
        'amount':         payment.amount,
        'method':         payment.get_method_display(),
    }


def render_html(receipt, template='receipts/receipt_print.html'):
    return render_to_string(template, {
        'org': receipt.organization,
        'r':   receipt_context(receipt),
        'receipt': receipt,
    })


def render_pdf(receipt):
    """
    Render the receipt to PDF bytes, or return None if WeasyPrint's native
    libraries are unavailable (caller should serve HTML instead).
    """
    try:
        from weasyprint import HTML
    except Exception:
        logger.info('WeasyPrint unavailable — falling back to HTML receipt.')
        return None

    html = render_html(receipt, template='receipts/receipt_pdf.html')
    try:
        return HTML(string=html).write_pdf()
    except Exception:
        logger.exception('WeasyPrint failed to render receipt %s',
                         receipt.receipt_number)
        return None
