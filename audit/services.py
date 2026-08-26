"""
Audit logging service. Financial and other sensitive operations call
log_action() to record an immutable trail. Logging must never break the
business operation, so failures here are swallowed (best-effort).
"""
import logging
from .models import AuditLog

logger = logging.getLogger(__name__)


class Action:
    PAYMENT_CLAIM_CREATED = 'PAYMENT_CLAIM_CREATED'
    PAYMENT_RECORDED = 'PAYMENT_RECORDED'
    PAYMENT_VERIFIED = 'PAYMENT_VERIFIED'
    PAYMENT_REJECTED = 'PAYMENT_REJECTED'
    PAYMENT_REVERSED = 'PAYMENT_REVERSED'
    RECEIPT_ISSUED = 'RECEIPT_ISSUED'
    RENT_GENERATED = 'RENT_GENERATED'
    CHARGE_CREATED = 'CHARGE_CREATED'
    ADJUSTMENT_CREATED = 'ADJUSTMENT_CREATED'
    DEPOSIT_MOVED = 'DEPOSIT_MOVED'
    TENANCY_TRANSFERRED = 'TENANCY_TRANSFERRED'
    TENANCY_ENDED = 'TENANCY_ENDED'
    TENANCY_TERMINATED = 'TENANCY_TERMINATED'
    TRANSFER_CREATED = 'TRANSFER_CREATED'
    MOVEOUT_CREATED = 'MOVEOUT_CREATED'
    OPENING_BALANCE_CREATED = 'OPENING_BALANCE_CREATED'
    SETTINGS_UPDATED = 'SETTINGS_UPDATED'
    USER_CREATED = 'USER_CREATED'
    USER_PERMISSION_CHANGED = 'USER_PERMISSION_CHANGED'


def get_client_ip(request):
    """Best-effort client IP extraction."""
    if request is None:
        return ''
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '') or ''


def log_action(action, actor=None, organization=None, obj=None,
               before=None, after=None, reason='', ip=''):
    """
    Write one immutable audit entry. Best-effort — never raises into the
    caller (a logging failure must not roll back a financial transaction).
    """
    try:
        object_type = object_id = object_repr = ''
        if obj is not None:
            object_type = obj.__class__.__name__
            object_id = str(getattr(obj, 'pk', '') or '')
            object_repr = str(obj)[:255]

        if organization is None and obj is not None:
            organization = getattr(obj, 'organization', None)

        return AuditLog.objects.create(
            organization=organization,
            actor=actor if (actor and getattr(actor, 'pk', None)) else None,
            action=action,
            object_type=object_type,
            object_id=object_id,
            object_repr=object_repr,
            ip=ip or '',
            before=before,
            after=after,
            reason=reason or '',
        )
    except Exception:  # pragma: no cover - logging must never break ops
        logger.exception('Failed to write audit log for action=%s', action)
        return None
