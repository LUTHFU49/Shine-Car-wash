from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """
    Generic security / activity audit trail. Populated by the
    AuditLogMiddleware for state-changing requests (POST/PUT/PATCH/DELETE)
    and by explicit calls from views/signals for domain events
    (e.g. "booking cancelled", "refund issued").
    """

    class Action(models.TextChoices):
        CREATE = 'create', 'Create'
        UPDATE = 'update', 'Update'
        DELETE = 'delete', 'Delete'
        LOGIN = 'login', 'Login'
        LOGOUT = 'logout', 'Logout'
        VIEW = 'view', 'View'
        OTHER = 'other', 'Other'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='audit_logs',
    )
    action = models.CharField(max_length=20, choices=Action.choices, default=Action.OTHER)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=255, blank=True)
    path = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=10, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(blank=True, null=True, help_text='Extra structured context for this event.')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'audit_logs_entry'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action']),
            models.Index(fields=['model_name']),
        ]

    def __str__(self):
        who = self.user.username if self.user else 'Anonymous'
        return f'{who} - {self.get_action_display()} - {self.created_at:%Y-%m-%d %H:%M}'
