from django.contrib import admin

from .models import Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('license_plate', 'display_name', 'customer', 'vehicle_type', 'status', 'created_at')
    list_filter = ('status', 'vehicle_type', 'make')
    search_fields = ('license_plate', 'make', 'model', 'customer__first_name', 'customer__last_name', 'customer__phone_number')
    readonly_fields = ('public_id', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    autocomplete_fields = ('customer',)

    fieldsets = (
        (None, {'fields': ('customer', 'license_plate', 'make', 'model', 'year', 'color', 'vehicle_type')}),
        ('Status & Media', {'fields': ('status', 'photo', 'notes')}),
        ('Metadata', {'fields': ('created_by', 'public_id', 'created_at', 'updated_at')}),
    )
