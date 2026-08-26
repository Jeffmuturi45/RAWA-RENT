from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """
    Redirects tenant users to the password change page on first login
    if must_change_password is True.

    Exempt URLs: logout, password change itself, static/media files.
    """

    EXEMPT_URLS = [
        '/accounts/login/',
        '/accounts/logout/',
        '/accounts/password-change/',
        '/static/',
        '/media/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and request.user.must_change_password
            and not any(
                request.path.startswith(url)
                for url in self.EXEMPT_URLS
            )
        ):
            return redirect('accounts:password_change')

        return self.get_response(request)
