"""
Celery tasks for finance app.

Key rules enforced here:
  1. Deposit is charged ONCE per tenancy (is_deposit_charge=True guard).
  2. Rent notice generation is idempotent (UniqueConstraint on tenancy+period_start).
  3. All DB writes are wrapped in transactions so partial failures roll back.
"""
import logging
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# HELPER: compute period dates for a tenancy
# ─────────────────────────────────────────

def _get_current_period(tenancy, reference_date=None):
    """
    Returns (period_start, period_end, due_date) for the billing cycle
    that contains or follows reference_date.

    billing_day=1  → period 2026-08-01 to 2026-08-31, due 2026-08-01
    billing_day=5  → period 2026-08-05 to 2026-09-04, due 2026-08-05
    """
    today = reference_date or date.today()
    bd = tenancy.billing_day  # 1, 5, 10, or 15

    # Find the billing date in the current month
    try:
        period_start = today.replace(day=bd)
    except ValueError:
        # bd=31 but month has 30 days etc — use last day
        import calendar
        last = calendar.monthrange(today.year, today.month)[1]
        period_start = today.replace(day=min(bd, last))

    # If today is before this month's billing day, go back one month
    if today < period_start:
        period_start = period_start - relativedelta(months=1)

    period_end = period_start + relativedelta(months=1) - timedelta(days=1)
    due_date = period_start  # rent is due on the billing day

    return period_start, period_end, due_date


# ─────────────────────────────────────────
# TASK 1: Generate rent notices (+ deposit if first time)
# ─────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_rent_notices(self, organization_id=None):
    """
    Called daily at 07:00 by Celery Beat, OR triggered manually by admin.

    For each ACTIVE tenancy whose billing_day == today:
      - Create a Charge (RENT) if not already existing for this period
      - Create a RentNotice linked to that charge
      - If no deposit charge exists for this tenancy, create one (once only)
      - Send in-app notification to tenant

    Passing organization_id restricts generation to one org (used by
    the admin "Generate Rents" button).
    """
    from tenancies.models import Tenancy
    from finance.models import (
        Charge, RentNotice, DepositAccount, DepositMovement
    )
    from notifications.models import notify

    today = date.today()
    generated = 0
    skipped = 0
    errors = 0

    qs = Tenancy.objects.filter(status='ACTIVE').select_related(
        'tenant', 'tenant__user', 'unit', 'unit__prop', 'organization'
    )
    if organization_id:
        qs = qs.filter(organization_id=organization_id)

    for tenancy in qs:
        try:
            period_start, period_end, due_date = _get_current_period(
                tenancy, today)

            # ── Only generate on billing day ──────────────────
            if today.day != tenancy.billing_day:
                skipped += 1
                continue

            with transaction.atomic():

                # ── 1. Deposit charge — once per tenancy ─────────
                deposit_exists = Charge.objects.filter(
                    tenancy=tenancy,
                    is_deposit_charge=True,
                ).exists()

                if not deposit_exists and tenancy.required_deposit > 0:
                    deposit_charge = Charge.objects.create(
                        organization=tenancy.organization,
                        tenancy=tenancy,
                        charge_type=Charge.Type.DEPOSIT,
                        description='Security Deposit',
                        amount=tenancy.required_deposit,
                        due_date=tenancy.start_date,
                        is_deposit_charge=True,
                    )
                    # Mirror in DepositAccount
                    deposit_account, _ = DepositAccount.objects.get_or_create(
                        tenancy=tenancy,
                        defaults={
                            'organization': tenancy.organization,
                            'required_amount': tenancy.required_deposit,
                        }
                    )
                    logger.info(
                        'Deposit charge created for tenancy %s — KSh %s',
                        tenancy.id, tenancy.required_deposit
                    )

                # ── 2. Rent charge (idempotent) ───────────────────
                charge, charge_created = Charge.objects.get_or_create(
                    tenancy=tenancy,
                    charge_type=Charge.Type.RENT,
                    period_start=period_start,
                    defaults={
                        'organization':  tenancy.organization,
                        'description':   f'Rent — {period_start.strftime("%B %Y")}',
                        'period_end':    period_end,
                        'amount':        tenancy.monthly_rent,
                        'due_date':      due_date,
                    }
                )

                # ── 3. Rent notice (idempotent) ───────────────────
                notice, notice_created = RentNotice.objects.get_or_create(
                    tenancy=tenancy,
                    period_start=period_start,
                    defaults={
                        'organization': tenancy.organization,
                        'charge':       charge,
                        'amount':       tenancy.monthly_rent,
                        'period_end':   period_end,
                        'due_date':     due_date,
                    }
                )

                if notice_created:
                    generated += 1
                    # ── 4. Notify tenant ──────────────────────────
                    tenant_user = getattr(tenancy.tenant, 'user', None)
                    if tenant_user:
                        notify(
                            recipient=tenant_user,
                            message=(
                                f'Your rent of KSh {tenancy.monthly_rent:,.0f} '
                                f'for {period_start.strftime("%B %Y")} is due on '
                                f'{due_date.strftime("%d %b %Y")}.'
                            ),
                            url='/portal/notices/',
                            level='warning',
                            notification_type='RENT_DUE',
                            organization=tenancy.organization,
                        )
                    logger.info(
                        'Rent notice created: tenancy=%s period=%s',
                        tenancy.id, period_start
                    )
                else:
                    skipped += 1

        except Exception as exc:
            errors += 1
            logger.error(
                'Error generating notice for tenancy %s: %s',
                tenancy.id, exc, exc_info=True
            )
            # Retry the whole task if something systemic went wrong
            if errors == 1:
                raise self.retry(exc=exc)

    logger.info(
        'generate_rent_notices complete — generated=%s skipped=%s errors=%s',
        generated, skipped, errors
    )
    return {'generated': generated, 'skipped': skipped, 'errors': errors}


# ─────────────────────────────────────────
# TASK 2: Mark overdue charges
# ─────────────────────────────────────────

@shared_task
def mark_overdue_charges():
    """
    Charges whose due_date has passed and are still unpaid are flagged
    overdue. Since `status` is a @property derived from allocations,
    this task just logs a summary — no DB update needed for status.
    But we DO send overdue notifications to tenants who haven't paid.
    """
    from finance.models import Charge, RentNotice
    from notifications.models import notify

    today = date.today()
    notified = 0

    # Find notices that are overdue and still PENDING or REJECTED
    overdue_notices = RentNotice.objects.filter(
        due_date__lt=today,
        status__in=['PENDING', 'REJECTED'],
    ).select_related(
        'tenancy', 'tenancy__tenant', 'tenancy__tenant__user',
        'tenancy__organization'
    )

    for notice in overdue_notices:
        tenant_user = getattr(notice.tenancy.tenant, 'user', None)
        if not tenant_user:
            continue

        # Don't spam — only notify once per overdue notice
        # Check if we already sent an overdue notification today
        from notifications.models import Notification
        already_notified = Notification.objects.filter(
            recipient=tenant_user,
            notification_type='RENT_DUE',
            created_at__date=today,
            message__contains='overdue',
        ).exists()

        if not already_notified:
            days_overdue = (today - notice.due_date).days
            notify(
                recipient=tenant_user,
                message=(
                    f'Your rent of KSh {notice.amount:,.0f} for '
                    f'{notice.period_start.strftime("%B %Y")} is '
                    f'{days_overdue} day(s) overdue. Please pay immediately.'
                ),
                url='/portal/notices/',
                level='danger',
                notification_type='RENT_DUE',
                organization=notice.tenancy.organization,
            )
            notified += 1

    logger.info('mark_overdue_charges — notified %s tenants', notified)
    return {'notified': notified}


# ─────────────────────────────────────────
# TASK 3: Rent-due reminders (3 days before)
# ─────────────────────────────────────────

@shared_task
def send_rent_due_reminders():
    """
    Every morning: find notices due in exactly 3 days and remind tenant.
    """
    from finance.models import RentNotice
    from notifications.models import notify

    reminder_date = date.today() + timedelta(days=3)
    notified = 0

    notices = RentNotice.objects.filter(
        due_date=reminder_date,
        status='PENDING',
    ).select_related(
        'tenancy', 'tenancy__tenant', 'tenancy__tenant__user',
        'tenancy__organization'
    )

    for notice in notices:
        tenant_user = getattr(notice.tenancy.tenant, 'user', None)
        if tenant_user:
            notify(
                recipient=tenant_user,
                message=(
                    f'Reminder: Your rent of KSh {notice.amount:,.0f} for '
                    f'{notice.period_start.strftime("%B %Y")} is due in 3 days '
                    f'({notice.due_date.strftime("%d %b %Y")}). '
                    f'Please upload proof of payment.'
                ),
                url='/portal/notices/',
                level='warning',
                notification_type='RENT_DUE',
                organization=notice.tenancy.organization,
            )
            notified += 1

    logger.info('send_rent_due_reminders — notified %s tenants', notified)
    return {'notified': notified}


# ─────────────────────────────────────────
# TASK 4: Admin-triggered bulk generation
# ─────────────────────────────────────────

# finance/tasks.py - Update admin_generate_rents_for_org

@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def admin_generate_rents_for_org(self, organization_id, triggered_by_user_id=None):
    """
    Called when admin clicks "Generate Rents" button.
    Runs generate_rent_notices restricted to one org,
    then notifies the admin of the result.
    """
    from notifications.models import notify
    from accounts.models import User

    try:
        result = generate_rent_notices(organization_id=organization_id)

        # Send notification to admin
        if triggered_by_user_id:
            try:
                admin_user = User.objects.get(id=triggered_by_user_id)
                from django.core.mail import send_mail
                from django.conf import settings

                # Send in-app notification
                notify(
                    recipient=admin_user,
                    message=(
                        f'✅ Rent generation complete: '
                        f'{result["generated"]} notices created, '
                        f'{result["skipped"]} skipped, '
                        f'{result["errors"]} errors.'
                    ),
                    url='/finance/rent-notices/',
                    level='success' if result['errors'] == 0 else 'warning',
                    notification_type='GENERAL',
                )

                # Optionally send email
                if result['errors'] > 0:
                    send_mail(
                        subject='Rent Generation - Errors Occurred',
                        message=(
                            f'Rent generation completed with errors.\n\n'
                            f'Generated: {result["generated"]}\n'
                            f'Skipped: {result["skipped"]}\n'
                            f'Errors: {result["errors"]}\n\n'
                            f'Please check the logs for details.'
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[admin_user.email],
                        fail_silently=True,
                    )

            except User.DoesNotExist:
                pass

        return result

    except Exception as exc:
        logger.error('admin_generate_rents_for_org failed: %s',
                     exc, exc_info=True)
        raise self.retry(exc=exc)
