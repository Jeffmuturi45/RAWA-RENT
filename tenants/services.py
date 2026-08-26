from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils.text import slugify
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


@transaction.atomic
def create_tenant_with_portal_account(
    organization,
    full_name,
    phone,
    email='',
    national_id='',
    address='',
    emergency_contact='',
    emergency_phone='',
    emergency_relation='',
    notes='',
    created_by=None,
):
    """
    Creates a Tenant record and automatically provisions a portal User account.

    Rules:
    - Email is required for portal access. If none provided, portal account
      is skipped gracefully (tenant can still be registered).
    - Default password = phone number (tenant must change on first login).
    - Role is always TENANT — never staff.
    - Everything is wrapped in atomic() so a failed user creation
      does not leave an orphaned Tenant record.

    Returns: (tenant, user, portal_created)
    """
    from tenants.models import Tenant

    # ── 1. Create the Tenant record ───────────────────────
    tenant = Tenant(
        organization=organization,
        full_name=full_name,
        phone=phone,
        email=email,
        national_id=national_id,
        address=address,
        emergency_contact=emergency_contact,
        emergency_phone=emergency_phone,
        emergency_relation=emergency_relation,
        notes=notes,
    )
    tenant.save()  # triggers tenant_number generation

    # ── 2. Provision portal account if email provided ─────
    user = None
    portal_created = False

    if email:
        # Check if a user with this email already exists
        if User.objects.filter(email=email).exists():
            logger.warning(
                f'Portal account skipped for tenant {tenant.tenant_number}: '
                f'email {email} already in use.'
            )
        else:
            user = User(
                email=email,
                full_name=full_name,
                phone=phone,
                role=User.Role.TENANT,
                organization=organization,
                must_change_password=True,
                is_active=True,
                is_staff=False,
            )
            # Default password = phone number
            user.set_password(phone)
            user.save()

            # Link user ↔ tenant
            tenant.user = user
            tenant.save(update_fields=['user'])

            portal_created = True
            logger.info(
                f'Portal account created for tenant {tenant.tenant_number} '
                f'({email})'
            )

    return tenant, user, portal_created


@transaction.atomic
def update_tenant_portal_account(tenant, full_name=None, phone=None, email=None):
    """
    Keeps the portal User account in sync when tenant details change.
    Never changes the password — only name, phone, email.
    """
    user = getattr(tenant, 'user', None)
    if not user:
        return

    changed = False

    if full_name and user.full_name != full_name:
        user.full_name = full_name
        changed = True

    if phone and user.phone != phone:
        user.phone = phone
        changed = True

    if email and user.email != email:
        # Check no conflict
        if not User.objects.filter(email=email).exclude(pk=user.pk).exists():
            user.email = email
            changed = True

    if changed:
        user.save()
