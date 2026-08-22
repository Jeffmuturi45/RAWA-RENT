"""Injects notification data for the topbar bell on every authenticated request."""
from .models import Notification


def notifications(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'unread_notifications_count': 0, 'recent_notifications': []}

    qs = Notification.objects.filter(recipient=user)
    return {
        'unread_notifications_count': qs.filter(is_read=False).count(),
        'recent_notifications': list(qs[:5]),
    }
