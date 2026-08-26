from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def tenant_required(view_func):
    """
    Ensures the logged-in user is a TENANT role with a linked tenant profile.
    Redirects non-tenants to the staff dashboard.
    Redirects unauthenticated users to the login page.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')

        if request.user.role != 'TENANT':
            messages.error(
                request, 'Access denied — staff accounts use the main dashboard.')
            return redirect('core:dashboard')

        if not hasattr(request.user, 'tenant_profile') or \
                request.user.tenant_profile is None:
            messages.error(
                request, 'Your account is not linked to a tenant profile.')
            return redirect('accounts:login')

        return view_func(request, *args, **kwargs)
    return wrapper
