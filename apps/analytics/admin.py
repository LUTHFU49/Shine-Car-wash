from django.contrib import admin

from .models import DashboardPreference


@admin.register(DashboardPreference)
class DashboardPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'updated_at')
    search_fields = ('user__username', 'user__email')
    autocomplete_fields = ('user',)
    readonly_fields = ('created_at', 'updated_at')
