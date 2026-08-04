from django.conf import settings
from django.db import models


class DashboardPreference(models.Model):
    """Which analytics widgets a user has chosen to show on their
    dashboard, and in what order. One row per user; created lazily
    with a sensible default set the first time someone visits the
    dashboard (see apps.analytics.widgets.DEFAULT_WIDGET_KEYS)."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='dashboard_preference')
    visible_widgets = models.JSONField(default=list, help_text='Ordered list of widget keys to display.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_dashboard_preference'

    def __str__(self):
        return f'Dashboard preference for {self.user}'
