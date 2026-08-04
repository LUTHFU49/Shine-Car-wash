from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'level', 'is_read', 'created_at')
    list_filter = ('level', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'recipient__username', 'recipient__email')
    readonly_fields = ('public_id', 'created_at', 'read_at')
    autocomplete_fields = ('recipient',)
