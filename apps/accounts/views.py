from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.models import Group
from django.conf import settings
from django.contrib.sessions.models import Session
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.audit_logs.models import AuditLog
from apps.core.redirects import safe_redirect_target

from .emails import (
    send_account_deactivated_email,
    send_new_device_login_email,
    send_password_changed_email,
    send_password_reset_email,
    send_verification_email,
)
from .forms import (
    AccountDeletionForm,
    ChangePasswordForm,
    ForgotPasswordForm,
    LoginForm,
    ProfileForm,
    ProfilePhotoForm,
    RegistrationForm,
    SetNewPasswordForm,
)
from .models import (
    EmailVerificationToken, LoginAuditEntry, Role, User, UserSession,
    record_password_history, revoke_sessions,
)


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _is_known_device(user, ip_address, user_agent):
    """
    "Known" = this exact IP + user-agent pair has a prior successful
    login for this user. Deliberately simple (no persistent device
    cookie/fingerprint) -- good enough to flag genuinely new logins
    (new location, new browser, credential stuffing from an unfamiliar
    machine) for a security email, without adding a device-trust system
    this app doesn't otherwise need (there's no 2FA to skip here).
    """
    return LoginAuditEntry.objects.filter(
        user=user, was_successful=True, ip_address=ip_address, user_agent=user_agent,
    ).exists()


def _role_redirect_url(user):
    """Every role lands on the same dashboard home for now -- per-role
    dashboard widgets are rendered from a single view (see dashboard app),
    branching by `request.user.role` rather than separate URLs."""
    return reverse('dashboard:home')


# ============================================================
# REGISTRATION
# ============================================================

@ratelimit(key='ip', rate=settings.RATELIMIT_REGISTER, method='POST', block=True)
def register_view(request):
    if request.user.is_authenticated:
        return redirect(_role_redirect_url(request.user))

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            user = User.objects.create_user(
                username=data['username'],
                email=data['email'],
                password=data['password1'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                phone_number=data['phone_number'],
                role=Role.CUSTOMER,
            )
            customer_group = Group.objects.filter(name='Customer').first()
            if customer_group:
                user.groups.add(customer_group)

            messages.success(
                request,
                'Account created! Check your email to verify your address, '
                'then log in below.',
            )
            return redirect('accounts:login')
    else:
        form = RegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


# ============================================================
# LOGIN / LOGOUT
# ============================================================

# Two independent throttles: by IP (stops one attacker cycling through
# many usernames) and by the submitted username (stops a distributed
# attack -- many IPs -- targeting one account). The per-account lockout
# in the POST handler below is a third, stricter layer specific to a
# single real account; this pair protects the endpoint itself.
@ratelimit(key='post:username', rate=settings.RATELIMIT_LOGIN, method='POST', block=True)
@ratelimit(key='ip', rate=settings.RATELIMIT_LOGIN, method='POST', block=True)
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_role_redirect_url(request.user))

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username_input = form.cleaned_data['username']
            password = form.cleaned_data['password']
            remember_me = form.cleaned_data['remember_me']

            existing_user = User.objects.filter(username__iexact=username_input).first() \
                or User.objects.filter(email__iexact=username_input).first()

            if existing_user and existing_user.is_locked_out:
                LoginAuditEntry.objects.create(
                    user=existing_user, username_attempted=username_input, was_successful=False,
                    ip_address=_client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
                    reason='account_locked',
                )
                messages.error(
                    request,
                    'This account is temporarily locked due to too many failed login attempts. '
                    'Please try again in a few minutes.',
                )
                return render(request, 'accounts/login.html', {'form': form})

            # Checked here, before authenticate(): Django's ModelBackend
            # rejects is_active=False users internally (user_can_authenticate),
            # so authenticate() would return None for a deactivated account
            # and we'd never reach a "user is not None" branch to explain why.
            if existing_user and existing_user.is_deactivated:
                LoginAuditEntry.objects.create(
                    user=existing_user, username_attempted=username_input, was_successful=False,
                    ip_address=_client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
                    reason='account_deactivated',
                )
                messages.error(
                    request,
                    'This account has been deactivated. Contact support if you believe this is a mistake.',
                )
                return render(request, 'accounts/login.html', {'form': form})

            user = authenticate(request, username=username_input, password=password)

            if user is not None:
                if existing_user:
                    existing_user.failed_login_attempts = 0
                    existing_user.locked_until = None
                    existing_user.save(update_fields=['failed_login_attempts', 'locked_until'])

                login(request, user)

                if remember_me:
                    request.session.set_expiry(settings.SESSION_COOKIE_AGE)
                else:
                    request.session.set_expiry(0)  # expires when browser closes

                ip_address = _client_ip(request)
                user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
                # Checked BEFORE writing this login's own entry below, so
                # it only ever reflects prior logins -- otherwise every
                # login would trivially "recognize" itself. Also skipped
                # entirely on an account's very first-ever successful
                # login, since the welcome email already covers that and
                # there's nothing to compare it against yet.
                has_logged_in_before = LoginAuditEntry.objects.filter(user=user, was_successful=True).exists()
                is_new_device = has_logged_in_before and not _is_known_device(user, ip_address, user_agent)

                LoginAuditEntry.objects.create(
                    user=user, username_attempted=username_input, was_successful=True,
                    ip_address=ip_address, user_agent=user_agent,
                )
                AuditLog.objects.create(
                    user=user, action=AuditLog.Action.LOGIN, description=f'{user.username} logged in',
                    ip_address=ip_address,
                )
                if is_new_device:
                    send_new_device_login_email(user, ip_address, user_agent, timezone.now())

                messages.success(request, f'Welcome back, {user.first_name or user.username}!')
                next_url = request.POST.get('next') or request.GET.get('next')
                return redirect(safe_redirect_target(request, next_url, _role_redirect_url(user)))

            # Authentication failed -- track attempts against the found account (if any)
            reason = 'invalid_credentials'
            if existing_user:
                existing_user.failed_login_attempts += 1
                if existing_user.failed_login_attempts >= settings.ACCOUNT_LOCKOUT_ATTEMPTS:
                    existing_user.locked_until = timezone.now() + timedelta(minutes=settings.ACCOUNT_LOCKOUT_MINUTES)
                    reason = 'account_locked_now'
                existing_user.save(update_fields=['failed_login_attempts', 'locked_until'])

            LoginAuditEntry.objects.create(
                user=existing_user, username_attempted=username_input, was_successful=False,
                ip_address=_client_ip(request), user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
                reason=reason,
            )
            messages.error(request, 'Incorrect username/email or password.')
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form})


@login_required
@require_POST
def logout_view(request):
    session_key = request.session.session_key
    AuditLog.objects.create(
        user=request.user, action=AuditLog.Action.LOGOUT,
        description=f'{request.user.username} logged out', ip_address=_client_ip(request),
    )
    logout(request)
    UserSession.objects.filter(session_key=session_key).delete()
    messages.info(request, 'You have been logged out.')
    return redirect('core:landing')


# ============================================================
# PASSWORD RESET
# ============================================================

# By email as well as IP: a bare IP limit alone wouldn't stop someone
# mail-bombing one victim's inbox with reset links from many IPs/proxies.
@ratelimit(key='post:email', rate=settings.RATELIMIT_PASSWORD_RESET_REQUEST_EMAIL, method='POST', block=True)
@ratelimit(key='ip', rate=settings.RATELIMIT_PASSWORD_RESET_REQUEST_IP, method='POST', block=True)
def forgot_password_view(request):
    """
    Always shows the same generic confirmation message regardless of
    whether the email exists, to prevent account enumeration -- but only
    actually sends a reset email when the account is real.
    """
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = User.objects.filter(email__iexact=email, is_deactivated=False).first()

            if user:
                uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                reset_path = reverse('accounts:password_reset_confirm', kwargs={'uidb64': uidb64, 'token': token})
                scheme = 'http' if settings.DEBUG else 'https'
                reset_url = f'{scheme}://{settings.SITE_DOMAIN}{reset_path}'
                send_password_reset_email(user, reset_url)

            messages.success(
                request,
                'If an account exists with that email, a password reset link has been sent.',
            )
            return redirect('accounts:login')
    else:
        form = ForgotPasswordForm()

    return render(request, 'accounts/forgot_password.html', {'form': form})


@ratelimit(key='ip', rate=settings.RATELIMIT_PASSWORD_RESET_CONFIRM, block=True)
def password_reset_confirm_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    token_valid = user is not None and default_token_generator.check_token(user, token)

    if not token_valid:
        return render(request, 'accounts/reset_link_invalid.html', status=400)

    if request.method == 'POST':
        form = SetNewPasswordForm(request.POST, user=user)
        if form.is_valid():
            record_password_history(user)
            user.set_password(form.cleaned_data['password1'])
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save()
            revoke_sessions(user)
            send_password_changed_email(user)
            AuditLog.objects.create(
                user=user, action=AuditLog.Action.UPDATE, description='Password reset via forgot-password flow',
            )
            messages.success(request, 'Your password has been reset. You can now log in.')
            return redirect('accounts:login')
    else:
        form = SetNewPasswordForm(user=user)

    return render(request, 'accounts/reset_password_confirm.html', {'form': form})


# ============================================================
# EMAIL VERIFICATION
# ============================================================

def verify_email_view(request, token):
    verification = EmailVerificationToken.objects.filter(token=token).select_related('user').first()

    if not verification:
        return render(request, 'accounts/verify_email_result.html', {'success': False, 'reason': 'not_found'})

    if not verification.is_valid():
        return render(request, 'accounts/verify_email_result.html', {'success': False, 'reason': 'expired', 'user': verification.user})

    user = verification.user
    user.is_email_verified = True
    user.email_verified_at = timezone.now()
    user.save(update_fields=['is_email_verified', 'email_verified_at'])
    verification.delete()

    return render(request, 'accounts/verify_email_result.html', {'success': True, 'user': user})


@login_required
@ratelimit(key='user', rate=settings.RATELIMIT_RESEND_VERIFICATION, block=True)
def resend_verification_view(request):
    if request.user.is_email_verified:
        messages.info(request, 'Your email is already verified.')
        return redirect('accounts:profile')

    EmailVerificationToken.objects.filter(user=request.user).delete()
    expires_at = timezone.now() + timedelta(hours=2)
    token = EmailVerificationToken.objects.create(user=request.user, expires_at=expires_at)

    verification_path = reverse('accounts:verify_email', kwargs={'token': str(token.token)})
    scheme = 'http' if settings.DEBUG else 'https'
    verification_url = f'{scheme}://{settings.SITE_DOMAIN}{verification_path}'
    send_verification_email(request.user, verification_url)

    messages.success(request, 'Verification email sent. Please check your inbox.')
    return redirect('accounts:profile')


# ============================================================
# PROFILE
# ============================================================

@login_required
def profile_view(request):
    return render(request, 'accounts/profile.html', {
        'photo_form': ProfilePhotoForm(instance=request.user),
    })


@login_required
def profile_edit_view(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            AuditLog.objects.create(user=request.user, action=AuditLog.Action.UPDATE, description='Profile updated')
            messages.success(request, 'Your profile has been updated.')
            return redirect('accounts:profile')
    else:
        form = ProfileForm(instance=request.user)

    return render(request, 'accounts/profile_edit.html', {'form': form})


@login_required
@require_POST
def profile_photo_upload_view(request):
    """AJAX endpoint -- uploads without a full page reload."""
    form = ProfilePhotoForm(request.POST, request.FILES, instance=request.user)
    if form.is_valid():
        form.save()
        AuditLog.objects.create(user=request.user, action=AuditLog.Action.UPDATE, description='Profile photo updated')
        return JsonResponse({'success': True, 'photo_url': request.user.profile_photo.url})
    return JsonResponse({'success': False, 'errors': form.errors.get('profile_photo', ['Upload failed.'])}, status=400)


@login_required
@require_POST
def profile_photo_remove_view(request):
    if request.user.profile_photo:
        request.user.profile_photo.delete(save=False)
        request.user.profile_photo = None
        request.user.save(update_fields=['profile_photo'])
        AuditLog.objects.create(user=request.user, action=AuditLog.Action.UPDATE, description='Profile photo removed')
    return JsonResponse({'success': True})


@login_required
def change_password_view(request):
    if request.method == 'POST':
        form = ChangePasswordForm(request.POST, user=request.user)
        if form.is_valid():
            record_password_history(request.user)
            request.user.set_password(form.cleaned_data['new_password1'])
            request.user.must_change_password = False
            request.user.save()
            update_session_auth_hash(request, request.user)  # keep the user logged in
            revoked = revoke_sessions(request.user, keep_session_key=request.session.session_key)
            send_password_changed_email(request.user)
            AuditLog.objects.create(user=request.user, action=AuditLog.Action.UPDATE, description='Password changed')
            if revoked:
                messages.success(request, f'Your password has been changed. You were logged out of {revoked} other device(s).')
            else:
                messages.success(request, 'Your password has been changed.')
            return redirect('accounts:profile')
    else:
        form = ChangePasswordForm(user=request.user)

    return render(request, 'accounts/change_password.html', {'form': form})


@login_required
def delete_account_view(request):
    if request.method == 'POST':
        form = AccountDeletionForm(request.POST, user=request.user)
        if form.is_valid():
            user = request.user
            user.is_deactivated = True
            user.deactivated_at = timezone.now()
            user.is_active = False
            user.save()
            revoke_sessions(user)
            send_account_deactivated_email(user)
            AuditLog.objects.create(user=user, action=AuditLog.Action.UPDATE, description='Account deactivated by owner')
            logout(request)
            messages.success(request, 'Your account has been deactivated. We\'re sorry to see you go.')
            return redirect('core:landing')
    else:
        form = AccountDeletionForm(user=request.user)

    return render(request, 'accounts/delete_account.html', {'form': form})


# ============================================================
# ACTIVE SESSIONS ("where am I logged in")
# ============================================================

def _describe_user_agent(ua):
    """
    Small, dependency-free UA sniff -- good enough for a "Chrome on
    Windows" style label in the Active Sessions list. Not meant to be
    exhaustive; unrecognized strings just fall back to generic labels
    rather than guessing wrong.
    """
    if not ua:
        return 'Unknown device'

    if 'Edg/' in ua:
        browser = 'Edge'
    elif 'OPR/' in ua or 'Opera' in ua:
        browser = 'Opera'
    elif 'Chrome/' in ua and 'Chromium' not in ua:
        browser = 'Chrome'
    elif 'Firefox/' in ua:
        browser = 'Firefox'
    elif 'Safari/' in ua and 'Chrome/' not in ua:
        browser = 'Safari'
    else:
        browser = 'Unknown browser'

    if 'Windows' in ua:
        os_name = 'Windows'
    elif 'Mac OS X' in ua or 'Macintosh' in ua:
        os_name = 'macOS'
    elif 'Android' in ua:
        os_name = 'Android'
    elif 'iPhone' in ua or 'iPad' in ua:
        os_name = 'iOS'
    elif 'Linux' in ua:
        os_name = 'Linux'
    else:
        os_name = 'Unknown OS'

    return f'{browser} on {os_name}'


@login_required
def active_sessions_view(request):
    current_session_key = request.session.session_key
    sessions = UserSession.objects.filter(user=request.user).order_by('-last_activity')
    session_rows = [{
        'pk': s.pk,
        'ip_address': s.ip_address,
        'device': _describe_user_agent(s.user_agent),
        'created_at': s.created_at,
        'last_activity': s.last_activity,
        'is_current': s.session_key == current_session_key,
    } for s in sessions]
    return render(request, 'accounts/active_sessions.html', {
        'session_rows': session_rows,
        'inactivity_timeout_minutes': settings.SESSION_INACTIVITY_TIMEOUT_MINUTES,
    })


@login_required
@require_POST
def revoke_session_view(request, session_pk):
    session = get_object_or_404(UserSession, pk=session_pk, user=request.user)
    is_current = session.session_key == request.session.session_key

    Session.objects.filter(session_key=session.session_key).delete()
    session.delete()
    AuditLog.objects.create(
        user=request.user, action=AuditLog.Action.UPDATE,
        description='Revoked a login session' + (' (this device)' if is_current else ''),
        ip_address=_client_ip(request),
    )

    if is_current:
        logout(request)
        messages.success(request, 'You have been logged out of this device.')
        return redirect('accounts:login')

    messages.success(request, 'That device has been logged out.')
    return redirect('accounts:active_sessions')


@login_required
@require_POST
def revoke_other_sessions_view(request):
    revoked = revoke_sessions(request.user, keep_session_key=request.session.session_key)
    AuditLog.objects.create(
        user=request.user, action=AuditLog.Action.UPDATE,
        description=f'Logged out {revoked} other device(s)', ip_address=_client_ip(request),
    )
    if revoked:
        messages.success(request, f'Logged out {revoked} other device(s).')
    else:
        messages.info(request, 'No other active sessions were found.')
    return redirect('accounts:active_sessions')
