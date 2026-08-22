"""
Forces users flagged with must_change_password to change it before using
the app. Applies only to authenticated users; allows the change-password
page, logout, and static/media so the user can actually complete the flow.
"""
from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)

        if user is not None and user.is_authenticated \
                and getattr(user, 'must_change_password', False):

            allowed = {
                reverse('accounts:change_password'),
                reverse('accounts:logout'),
            }
            path = request.path

            is_allowed = (
                path in allowed
                or path.startswith('/static/')
                or path.startswith('/media/')
            )
            if not is_allowed:
                return redirect('accounts:change_password')

        return self.get_response(request)
