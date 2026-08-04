from .models import AuditLog

STATE_CHANGING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

# PUT/PATCH/DELETE map unambiguously to an action; POST is left as OTHER
# since it's used for creates, updates, logins, and one-off actions
# alike -- the views/signals that know which of those it is log a more
# specific, explicit AuditLog entry themselves (see e.g. apps.bookings.
# views._log). This middleware is only the safety net that guarantees
# nothing state-changing goes completely unrecorded.
METHOD_ACTION_MAP = {
    'PUT': AuditLog.Action.UPDATE,
    'PATCH': AuditLog.Action.UPDATE,
    'DELETE': AuditLog.Action.DELETE,
}

# Paths we never want to log noisily (static/media/health-checks).
SKIP_PREFIXES = ('/static/', '/media/', '/__debug__/')


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class AuditLogMiddleware:
    """
    Lightweight, always-on audit trail for every state-changing request.
    Fine-grained domain events (e.g. "booking #42 approved by manager X")
    are logged explicitly from within the relevant views/signals with
    richer `metadata`; this middleware is the safety-net that guarantees
    nothing state-changing goes unrecorded even if a view forgets to.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        try:
            if (
                request.method in STATE_CHANGING_METHODS
                and not request.path.startswith(SKIP_PREFIXES)
                and 200 <= response.status_code < 400
            ):
                AuditLog.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    action=METHOD_ACTION_MAP.get(request.method, AuditLog.Action.OTHER),
                    description=f'{request.method} {request.path}',
                    path=request.path,
                    method=request.method,
                    ip_address=_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
                )
        except Exception:
            # Auditing must never break the request/response cycle.
            pass

        return response
