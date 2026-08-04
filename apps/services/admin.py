from django.contrib import admin

from .models import Service, ServiceCategory


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'display_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)
    ordering = ('display_order', 'name')


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'duration_minutes', 'status', 'available_days_display')
    list_filter = ('status', 'category')
    search_fields = ('name', 'description')
    readonly_fields = ('public_id', 'created_at', 'updated_at')
    ordering = ('category__display_order', 'name')
    autocomplete_fields = ()

    fieldsets = (
        (None, {'fields': ('category', 'name', 'description', 'image')}),
        ('Pricing & Duration', {'fields': ('price', 'duration_minutes')}),
        ('Status & Availability', {'fields': ('status', 'available_days')}),
        ('Metadata', {'fields': ('created_by', 'public_id', 'created_at', 'updated_at')}),
    )
