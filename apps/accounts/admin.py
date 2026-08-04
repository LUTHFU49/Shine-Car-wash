from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session

from apps.audit_logs.models import AuditLog
from apps.audit_logs.utils import field_diff

from .models import EmailVerificationToken, LoginAuditEntry, PasswordHistory, User, UserSession, revoke_sessions


SECURITY_FIELDS = ['role', 'is_active', 'is_staff', 'is_superuser', 'is_deactivated']


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'role', 'is_email_verified', 'is_active', 'is_locked_out', 'created_at')
    list_filter = ('role', 'is_active', 'is_email_verified', 'is_deactivated')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone_number')
    ordering = ('-created_at',)
    readonly_fields = ('public_id', 'created_at', 'updated_at', 'failed_login_attempts', 'locked_until')
    actions = ['force_logout_everywhere', 'force_password_reset']

    fieldsets = DjangoUserAdmin.fieldsets + (
        ('ShineHub Profile', {
            'fields': ('role', 'phone_number', 'profile_photo', 'public_id'),
        }),
        ('Verification & Security', {
            'fields': ('is_email_verified', 'email_verified_at', 'failed_login_attempts', 'locked_until', 'must_change_password', 'is_deactivated', 'deactivated_at'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def is_locked_out(self, obj):
        return obj.is_locked_out
    is_locked_out.boolean = True
    is_locked_out.short_description = 'Locked'

    @admin.action(description='Force logout everywhere (revoke all sessions)')
    def force_logout_everywhere(self, request, queryset):
        total = sum(revoke_sessions(user) for user in queryset)
        self.message_user(request, f'Revoked {total} session(s) across {queryset.count()} user(s).')

    @admin.action(description='Force password reset on next login')
    def force_password_reset(self, request, queryset):
        count = queryset.update(must_change_password=True)
        revoked = sum(revoke_sessions(user) for user in queryset)
        for user in queryset:
            AuditLog.objects.create(
                user=request.user, action=AuditLog.Action.UPDATE,
                model_name='User', object_id=str(user.pk),
                description=f'Admin forced a password reset for "{user.username}"',
                ip_address=_client_ip(request),
            )
        self.message_user(request, f'{count} user(s) will be required to set a new password on next login ({revoked} existing session(s) also revoked).')

    def save_model(self, request, obj, form, change):
        if change:
            old = User.objects.get(pk=obj.pk)
            request._audit_old_fields = {f: getattr(old, f) for f in SECURITY_FIELDS}
            request._audit_old_groups = set(old.groups.values_list('name', flat=True))
        else:
            request._audit_old_fields = None
            request._audit_old_groups = set()

        super().save_model(request, obj, form, change)

        if not change:
            AuditLog.objects.create(
                user=request.user, action=AuditLog.Action.CREATE,
                model_name='User', object_id=str(obj.pk),
                description=f'Admin created user "{obj.username}"',
                ip_address=_client_ip(request),
            )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        if not change or request._audit_old_fields is None:
            return

        obj = form.instance
        new_values = {f: getattr(obj, f) for f in SECURITY_FIELDS}
        diff = field_diff(request._audit_old_fields, new_values)
        new_groups = set(obj.groups.values_list('name', flat=True))
        old_groups = request._audit_old_groups

        metadata = dict(diff) if diff else {}
        if new_groups != old_groups:
            metadata['groups_before'] = sorted(old_groups)
            metadata['groups_after'] = sorted(new_groups)

        if metadata:
            AuditLog.objects.create(
                user=request.user, action=AuditLog.Action.UPDATE,
                model_name='User', object_id=str(obj.pk),
                description=f'Admin updated "{obj.username}"',
                metadata=metadata, ip_address=_client_ip(request),
            )

    def delete_model(self, request, obj):
        AuditLog.objects.create(
            user=request.user, action=AuditLog.Action.DELETE,
            model_name='User', object_id=str(obj.pk),
            description=f'Admin deleted user "{obj.username}"',
            ip_address=_client_ip(request),
        )
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            AuditLog.objects.create(
                user=request.user, action=AuditLog.Action.DELETE,
                model_name='User', object_id=str(obj.pk),
                description=f'Admin bulk-deleted user "{obj.username}"',
                ip_address=_client_ip(request),
            )
        super().delete_queryset(request, queryset)


# Django registers a default GroupAdmin on import of django.contrib.auth.admin;
# unregister it so we can log permission-set changes (a Group's
# permissions ARE the RBAC permission set -- changing them changes what
# every user in that group can do, which is exactly what Phase 15 asks
# to be audited under "Permission changes").
admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin):
    def save_model(self, request, obj, form, change):
        if change:
            old_perms = set(
                Group.objects.get(pk=obj.pk).permissions.values_list('codename', flat=True),
            )
        else:
            old_perms = set()
        request._audit_old_group_perms = old_perms
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        new_perms = set(obj.permissions.values_list('codename', flat=True))
        old_perms = getattr(request, '_audit_old_group_perms', set())
        if new_perms != old_perms:
            AuditLog.objects.create(
                user=request.user, action=AuditLog.Action.UPDATE,
                model_name='Group', object_id=str(obj.pk),
                description=f'Admin changed permissions for group "{obj.name}"',
                metadata={
                    'permissions_before': sorted(old_perms),
                    'permissions_after': sorted(new_perms),
                },
                ip_address=_client_ip(request),
            )

    def delete_model(self, request, obj):
        AuditLog.objects.create(
            user=request.user, action=AuditLog.Action.DELETE,
            model_name='Group', object_id=str(obj.pk),
            description=f'Admin deleted group "{obj.name}"',
            ip_address=_client_ip(request),
        )
        super().delete_model(request, obj)


@admin.register(LoginAuditEntry)
class LoginAuditEntryAdmin(admin.ModelAdmin):
    list_display = ('username_attempted', 'was_successful', 'ip_address', 'reason', 'created_at')
    list_filter = ('was_successful',)
    search_fields = ('username_attempted', 'ip_address')
    readonly_fields = [f.name for f in LoginAuditEntry._meta.fields]
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'expires_at')
    readonly_fields = ('token', 'created_at')


@admin.register(PasswordHistory)
class PasswordHistoryAdmin(admin.ModelAdmin):
 
    list_display = ('user', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('user', 'hashed_password', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'ip_address', 'user_agent_short', 'created_at', 'last_activity')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'user__email', 'ip_address')
    readonly_fields = [f.name for f in UserSession._meta.fields]
    ordering = ('-last_activity',)
    actions = ['revoke_selected_sessions']

    def has_add_permission(self, request):
        return False

    def user_agent_short(self, obj):
        return (obj.user_agent[:60] + '…') if len(obj.user_agent) > 60 else obj.user_agent
    user_agent_short.short_description = 'User agent'

    @admin.action(description='Revoke selected sessions (force logout)')
    def revoke_selected_sessions(self, request, queryset):
        session_keys = list(queryset.values_list('session_key', flat=True))
        Session.objects.filter(session_key__in=session_keys).delete()
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f'Revoked {count} session(s).')
