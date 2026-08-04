from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'action', 'model_name', 'description', 'ip_address')
    list_filter = ('action', 'model_name', 'method')
    search_fields = ('path', 'description', 'model_name', 'object_id', 'user__username', 'ip_address')
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
