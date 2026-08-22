"""
Role-Based Access Control (RBAC) — single source of truth.

Capabilities are abstract permissions; each role maps to a set of them.
Views enforce capabilities via @require_capability; templates read the
`caps` dict injected by accounts.context_processors.rbac.
"""
from functools import wraps
from django.shortcuts import redirect, render

from .models import User

Role = User.Role


class Cap:
    """Capability constants."""
    VIEW_DASHBOARD = 'view_dashboard'
    VIEW_PROPERTIES = 'view_properties'
    MANAGE_PROPERTIES = 'manage_properties'
    VIEW_TENANTS = 'view_tenants'
    MANAGE_TENANTS = 'manage_tenants'
    VIEW_FINANCE = 'view_finance'
    MANAGE_FINANCE = 'manage_finance'
    RECORD_PAYMENT = 'record_payment'
    VERIFY_PAYMENT = 'verify_payment'
    MANAGE_USERS = 'manage_users'
    MANAGE_SETTINGS = 'manage_settings'
    VIEW_AUDIT = 'view_audit'


# Ordered list — used to build the template `caps` dict.
ALL_CAPS = [
    Cap.VIEW_DASHBOARD, Cap.VIEW_PROPERTIES, Cap.MANAGE_PROPERTIES,
    Cap.VIEW_TENANTS, Cap.MANAGE_TENANTS, Cap.VIEW_FINANCE,
    Cap.MANAGE_FINANCE, Cap.RECORD_PAYMENT, Cap.VERIFY_PAYMENT,
    Cap.MANAGE_USERS, Cap.MANAGE_SETTINGS, Cap.VIEW_AUDIT,
]


# ─────────────────────────────────────────
# ROLE → CAPABILITIES  (the confirmed matrix)
# ─────────────────────────────────────────
ROLE_CAPABILITIES = {
    Role.AGENCY_OWNER: set(ALL_CAPS),

    Role.MANAGER: {
        Cap.VIEW_DASHBOARD,
        Cap.VIEW_PROPERTIES, Cap.MANAGE_PROPERTIES,
        Cap.VIEW_TENANTS, Cap.MANAGE_TENANTS,
        Cap.VIEW_FINANCE, Cap.MANAGE_FINANCE, Cap.RECORD_PAYMENT,
        Cap.VERIFY_PAYMENT,
        Cap.VIEW_AUDIT,
    },

    Role.ACCOUNTS_OFFICER: {
        Cap.VIEW_DASHBOARD,
        Cap.VIEW_PROPERTIES,
        Cap.VIEW_TENANTS,
        Cap.VIEW_FINANCE, Cap.MANAGE_FINANCE, Cap.RECORD_PAYMENT,
        Cap.VERIFY_PAYMENT,
    },

    # Receptionist may CREATE payment claims but must never verify them (§28).
    Role.RECEPTIONIST: {
        Cap.VIEW_DASHBOARD,
        Cap.VIEW_PROPERTIES,
        Cap.VIEW_TENANTS, Cap.MANAGE_TENANTS,
        Cap.VIEW_FINANCE, Cap.RECORD_PAYMENT,
    },

    Role.TENANT: set(),
}


def has_capability(user, cap):
    """True if the user's role grants the capability. Superusers get everything."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return cap in ROLE_CAPABILITIES.get(user.role, set())


def capabilities_for(user):
    """Return the full {cap: bool} map for template use."""
    return {cap: has_capability(user, cap) for cap in ALL_CAPS}


def is_staff_user(user):
    """Staff = any authenticated non-TENANT user (or superuser)."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.role != Role.TENANT


# ─────────────────────────────────────────
# VIEW DECORATORS
# ─────────────────────────────────────────
def require_capability(cap):
    """
    Gate a view on a capability. Assumes @login_required runs first
    (unauthenticated users are redirected there). Authenticated users
    lacking the capability get a friendly 403.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('accounts:login')
            if not has_capability(request.user, cap):
                return render(request, '403.html', status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def staff_required(view_func):
    """
    Block TENANT-role users from the staff app, routing them to the
    portal placeholder. Unauthenticated users go to login.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not is_staff_user(request.user):
            return redirect('accounts:portal_placeholder')
        return view_func(request, *args, **kwargs)
    return _wrapped
