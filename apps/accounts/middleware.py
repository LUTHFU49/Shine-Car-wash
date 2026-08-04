"""
Session security for the accounts app.

SessionSecurityMiddleware does two things on every request, in order:

1. BEFORE the view runs: if the user is authenticated and their session
   has been idle longer than SESSION_INACTIVITY_TIMEOUT_MINUTES, log
   them out right there. request.user becomes AnonymousUser for the
   rest of this request, so any @login_required/@role_required view
   downstream naturally redirects to login -- we don't need to build a
   redirect ourselves or special-case which view this happened to hit.

2. AFTER the view runs: if the user is (still, or newly) authenticated,
   stamp the current time into the session as the new "last activity"
   marker, and refresh the matching apps.accounts.models.UserSession row
   (throttled to roughly once a minute per session, so this doesn't add
   a DB write to every single request).
"""

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import Resolver404, resolve
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.audit_logs.models import AuditLog

from .models import UserSession

SESSION_ACTIVITY_KEY = '_last_activity'
_TOUCH_THROTTLE_SECONDS = 60


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class SessionSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._enforce_inactivity_timeout(request)
        response = self.get_response(request)
        self._touch_session(request)
        return response

    def _enforce_inactivity_timeout(self, request):
        if not request.user.is_authenticated:
            return

        raw_last_activity = request.session.get(SESSION_ACTIVITY_KEY)
        if not raw_last_activity:
            return  # first request of this session -- nothing to compare against yet

        last_activity = parse_datetime(raw_last_activity)
        timeout = timedelta(minutes=settings.SESSION_INACTIVITY_TIMEOUT_MINUTES)
        if not last_activity or timezone.now() - last_activity <= timeout:
            return

        user = request.user
        session_key = request.session.session_key
        AuditLog.objects.create(
            user=user, action=AuditLog.Action.LOGOUT,
            description=f'{user.username} auto-logged-out after {settings.SESSION_INACTIVITY_TIMEOUT_MINUTES} min of inactivity',
            ip_address=_client_ip(request),
        )
        UserSession.objects.filter(session_key=session_key).delete()
        logout(request)
        messages.info(request, 'You were logged out after a period of inactivity. Please log in again.')

    def _touch_session(self, request):
        if not request.user.is_authenticated:
            return

        session_key = request.session.session_key
        if not session_key:
            return  # session was flushed (e.g. by the timeout logout above) -- nothing to touch

        now = timezone.now()
        request.session[SESSION_ACTIVITY_KEY] = now.isoformat()

        recently_touched = UserSession.objects.filter(
            session_key=session_key, last_activity__gte=now - timedelta(seconds=_TOUCH_THROTTLE_SECONDS),
        ).exists()
        if recently_touched:
            return

        UserSession.objects.update_or_create(
            session_key=session_key,
            defaults={
                'user': request.user,
                'ip_address': _client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:255],
                'last_activity': now,
            },
        )


class ForcePasswordChangeMiddleware:
    """
    If an admin has flagged request.user.must_change_password (see
    UserAdmin.force_password_reset), every request except the change-
    password page and logout gets redirected there with an explanation.
    Clears automatically once apps.accounts.views.change_password_view
    succeeds -- see the flag reset there.
    """
    EXEMPT_URL_NAMES = {'accounts:change_password', 'accounts:logout'}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and getattr(request.user, 'must_change_password', False):
            if self._current_url_name(request) not in self.EXEMPT_URL_NAMES:
                messages.warning(request, 'For security, please set a new password before continuing.')
                return redirect('accounts:change_password')
        return self.get_response(request)

    @staticmethod
    def _current_url_name(request):
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return None
        return f'{match.namespace}:{match.url_name}' if match.namespace else match.url_name
