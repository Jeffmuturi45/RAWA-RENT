class AuditMiddleware:
    """
    Placeholder audit middleware.
    Full implementation in Phase 0 audit build.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response
