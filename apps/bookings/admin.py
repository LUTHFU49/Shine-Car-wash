from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('booking_code_display', 'customer', 'vehicle', 'service', 'scheduled_date', 'scheduled_time', 'status', 'booking_type')
    list_filter = ('status', 'booking_type', 'scheduled_date')
    search_fields = ('customer__first_name', 'customer__last_name', 'vehicle__license_plate', 'service__name')
    readonly_fields = ('public_id', 'price_at_booking', 'duration_minutes_at_booking', 'created_at', 'updated_at', 'confirmation_email_sent_at', 'reminder_email_sent_at')
    ordering = ('-scheduled_date', '-scheduled_time')
    date_hierarchy = 'scheduled_date'
    autocomplete_fields = ('customer', 'vehicle', 'service')

    fieldsets = (
        (None, {'fields': ('customer', 'vehicle', 'service', 'booking_type', 'status')}),
        ('Schedule', {'fields': ('scheduled_date', 'scheduled_time')}),
        ('Pricing Snapshot', {'fields': ('price_at_booking', 'duration_minutes_at_booking')}),
        ('Notes', {'fields': ('notes', 'staff_notes')}),
        ('Cancellation', {'fields': ('cancelled_at', 'cancelled_by', 'cancellation_reason')}),
        ('Email Tracking', {'fields': ('confirmation_email_sent_at', 'reminder_email_sent_at')}),
        ('Metadata', {'fields': ('created_by', 'public_id', 'created_at', 'updated_at')}),
    )

    def booking_code_display(self, obj):
        return obj.booking_code
    booking_code_display.short_description = 'Booking Code'
