"""Template context processors for the accounts app."""
from .permissions import capabilities_for


def rbac(request):
    """
    Inject a `caps` dict of {capability: bool} for the current user so
    templates can gate UI, e.g. {% if caps.manage_users %}.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'caps': {}}
    return {'caps': capabilities_for(user)}
