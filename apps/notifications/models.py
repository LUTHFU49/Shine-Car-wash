import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationLevel(models.TextChoices):
    INFO = 'info', 'Info'
    SUCCESS = 'success', 'Success'
    WARNING = 'warning', 'Warning'
    DANGER = 'danger', 'Danger'


class Notification(models.Model):
    """
    Database-backed in-app notification. This is the foundation the
    Phase 11 real-time layer (Django Channels / WebSockets) will push
    over the wire -- for now the bell badge/list poll this table rather
    than receiving a live push. See apps.notifications.utils for the
    helpers other apps should call instead of creating rows directly.
    """
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')

    title = models.CharField(max_length=150)
    message = models.CharField(max_length=255, blank=True)
    level = models.CharField(max_length=10, choices=NotificationLevel.choices, default=NotificationLevel.INFO, db_index=True)
    url = models.CharField(max_length=255, blank=True, help_text='Where clicking this notification should take the user.')

    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'notifications_notification'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['recipient', 'is_read'])]

    def __str__(self):
        return f'{self.title} -> {self.recipient}'

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
