"""
Cross-cutting middleware for the core app.

Houses RatelimitMiddleware and SecurityHeadersMiddleware -- see each
class's docstring below.
"""

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render

from django_ratelimit.exceptions import Ratelimited


def _wants_json(request):
    """
    True for AJAX/polling/API-style requests, where a friendly HTML page
    would be silently swallowed by fetch()/XHR and never seen by anyone.
    Everything else (a human submitting a form) gets the branded page.
    """
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return True
    if request.content_type == 'application/json':
        return True
    accepts = request.headers.get('accept', '')
    return 'application/json' in accepts and 'text/html' not in accepts


class RatelimitMiddleware:
    """
    django-ratelimit's `@ratelimit(..., block=True)` raises `Ratelimited`
    rather than returning a response -- by design, so the same decorator
    works whether you want to render a page, return JSON, or just log
    and let the request through. This middleware is what actually turns
    that exception into a response for this project: a branded 429 page
    for normal browser requests, and a small JSON body for AJAX/polling
    endpoints (notification counts, payment status polling, etc.) so
    client-side JS can detect it and back off instead of erroring out.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not isinstance(exception, Ratelimited):
            return None

        if _wants_json(request):
            return JsonResponse(
                {'error': 'rate_limited', 'detail': 'Too many requests. Please slow down and try again shortly.'},
                status=429,
            )

        return render(request, 'errors/429.html', status=429)


def _build_csp_header(policy):
    return '; '.join(f'{directive} {" ".join(sources)}' for directive, sources in policy.items())


def _build_permissions_policy_header(policy):
    return ', '.join(f'{feature}=({" ".join(allowlist)})' for feature, allowlist in policy.items())


class SecurityHeadersMiddleware:
    """
    Adds Content-Security-Policy and Permissions-Policy to every
    response -- Django's SecurityMiddleware has no built-in setting for
    either, unlike X-Frame-Options/nosniff/Referrer-Policy which are
    already handled via settings (see the SECURE_* block in
    settings.py). Header content is built once at import time from
    settings.CONTENT_SECURITY_POLICY / settings.PERMISSIONS_POLICY
    rather than on every request.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.csp_header = _build_csp_header(settings.CONTENT_SECURITY_POLICY)
        self.permissions_policy_header = _build_permissions_policy_header(settings.PERMISSIONS_POLICY)

    def __call__(self, request):
        response = self.get_response(request)
        response['Content-Security-Policy'] = self.csp_header
        response['Permissions-Policy'] = self.permissions_policy_header
        return response
