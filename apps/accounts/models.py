import uuid

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    """
    The five user roles required by the system. Real permission
    enforcement is done through Django Groups (created in a data
    migration -- see apps/accounts/migrations/0002_create_roles.py),
    this field is a fast, queryable label used for UI branching,
    dashboards, and role-based redirects.
    """
    SUPER_ADMIN = 'super_admin', 'Super Admin'
    MANAGER = 'manager', 'Manager'
    CASHIER = 'cashier', 'Cashier'
    EMPLOYEE = 'employee', 'Employee'
    CUSTOMER = 'customer', 'Customer'


phone_validator = RegexValidator(
    regex=r'^\+?[0-9]{9,15}$',
    message='Enter a valid phone number (digits only, 9 to 15 digits, optional leading +).',
)


class User(AbstractUser):
    """
    Custom user model for ShineHub. Extends Django's AbstractUser so we
    keep all the battle-tested auth machinery (password hashing,
    permissions, is_staff/is_superuser, etc.) while adding the fields
    the system needs: role, phone, profile photo, and verification state.
    """
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    email = models.EmailField('email address', unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True)

    phone_number = models.CharField(
        max_length=17, validators=[phone_validator], blank=True,
        help_text='Digits only, e.g. 0712345678 or +254712345678',
    )

    profile_photo = models.ImageField(
        upload_to='profile_photos/%Y/%m/', blank=True, null=True,
        help_text='Square images work best. Max 5MB.',
    )

    is_email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(blank=True, null=True)

    # Brute-force protection
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)

    # Soft "deactivate my account" flow -- actual row is kept for audit /
    # financial record integrity, but the account is fully unusable.
    is_deactivated = models.BooleanField(default=False)
    deactivated_at = models.DateTimeField(blank=True, null=True)

    # Set by an admin (see UserAdmin.force_password_reset action) when an
    # account needs a fresh password before it can be used again -- a
    # newly-created staff account, or one suspected of compromise.
    # Enforced by apps.accounts.middleware.ForcePasswordChangeMiddleware,
    # which redirects every authenticated request except the change-
    # password page itself until this clears.
    must_change_password = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        db_table = 'accounts_user'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['email']),
        ]

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_role_display()})'

    @property
    def is_locked_out(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    @property
    def initials(self):
        first = (self.first_name or '')[:1]
        last = (self.last_name or '')[:1]
        combo = (first + last).upper()
        return combo or (self.username[:2].upper() if self.username else '??')


class EmailVerificationToken(models.Model):
    """One-time token emailed to a user to confirm their address."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='verification_token')
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'accounts_email_verification_token'

    def is_valid(self):
        return timezone.now() < self.expires_at

    def __str__(self):
        return f'Verification token for {self.user.username}'


class UserSession(models.Model):
    """
    One row per live Django session belonging to an authenticated user --
    populated/refreshed by apps.accounts.middleware.SessionSecurityMiddleware
    on each request, not by the login view alone, so it stays accurate as
    long as the underlying django.contrib.sessions.models.Session exists.

    Purpose: lets a user see "where am I logged in" (My Profile > Active
    Sessions) and revoke one or all of them, and lets an admin force a
    logout everywhere for an account that's been compromised or
    deactivated. Revoking = deleting the matching Session row (see
    apps.accounts.views.revoke_session_view) and this row; the browser's
    existing cookie will simply point at a session that no longer
    exists, so Django treats its next request as anonymous.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=40, unique=True, db_index=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_activity = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'accounts_user_session'
        ordering = ['-last_activity']

    def __str__(self):
        return f'{self.user.username} @ {self.ip_address or "unknown IP"} (last active {self.last_activity:%Y-%m-%d %H:%M})'


def revoke_sessions(user, keep_session_key=None):
    """
    Deletes every live Django session belonging to `user` (optionally
    sparing `keep_session_key` -- e.g. the browser that just changed
    the password) along with the matching UserSession rows. The
    browser holding a revoked session's cookie is treated as anonymous
    on its next request, since the session it points at no longer
    exists.

    Used by: change-password, password-reset-confirm, account
    deactivation, the self-service "log out everywhere" view, and the
    admin "force logout" action -- anywhere a security event should
    invalidate sessions this app doesn't have a live request for.
    Returns the number of sessions revoked.
    """
    from django.contrib.sessions.models import Session

    queryset = UserSession.objects.filter(user=user)
    if keep_session_key:
        queryset = queryset.exclude(session_key=keep_session_key)
    session_keys = list(queryset.values_list('session_key', flat=True))
    Session.objects.filter(session_key__in=session_keys).delete()
    queryset.delete()
    return len(session_keys)


class PasswordHistory(models.Model):
    """
    Stores the hash of a password a user is moving AWAY from (not the
    current one, which lives on User.password) so PasswordReuseValidator
    can block reuse of the last PASSWORD_HISTORY_COUNT passwords.
    Populated by apps.accounts.views.change_password_view and
    password_reset_confirm_view right before overwriting user.password;
    pruned to the configured count in the same call.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_history')
    hashed_password = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'accounts_password_history'
        ordering = ['-created_at']


def record_password_history(user):
    """
    Call this BEFORE overwriting user.password with a new one -- saves
    the password being replaced into history and prunes older rows
    beyond settings.PASSWORD_HISTORY_COUNT, so PasswordReuseValidator
    always has an accurate, bounded window to check against.
    """
    from django.conf import settings

    if not user.password:
        return  # nothing to save yet (e.g. brand-new account)

    PasswordHistory.objects.create(user=user, hashed_password=user.password)
    keep = settings.PASSWORD_HISTORY_COUNT
    stale_ids = list(
        PasswordHistory.objects.filter(user=user).order_by('-created_at').values_list('pk', flat=True)[keep:],
    )
    if stale_ids:
        PasswordHistory.objects.filter(pk__in=stale_ids).delete()


class LoginAuditEntry(models.Model):
    """Every login attempt (success or failure) -- feeds the Security Audit Logs app too."""
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='login_history')
    username_attempted = models.CharField(max_length=150)
    was_successful = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True)
    reason = models.CharField(max_length=100, blank=True, help_text='e.g. "invalid_password", "account_locked"')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'accounts_login_audit_entry'
        ordering = ['-created_at']
        verbose_name_plural = 'Login audit entries'

    def __str__(self):
        status = 'SUCCESS' if self.was_successful else 'FAILED'
        return f'[{status}] {self.username_attempted} @ {self.created_at:%Y-%m-%d %H:%M}'
