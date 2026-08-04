from django.contrib import admin

from .models import Feedback, Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('booking', 'customer', 'rating', 'is_published', 'has_response', 'created_at')
    list_filter = ('rating', 'is_published', 'created_at')
    search_fields = ('booking__vehicle__license_plate', 'customer__first_name', 'customer__last_name', 'comment')
    autocomplete_fields = ('booking', 'customer', 'responded_by')
    readonly_fields = ('public_id', 'created_at', 'updated_at', 'responded_at')


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('subject', 'customer', 'feedback_type', 'priority', 'status', 'created_at')
    list_filter = ('feedback_type', 'status', 'priority', 'created_at')
    search_fields = ('subject', 'message', 'customer__first_name', 'customer__last_name')
    autocomplete_fields = ('customer', 'booking', 'responded_by')
    readonly_fields = ('public_id', 'created_at', 'updated_at', 'responded_at')
