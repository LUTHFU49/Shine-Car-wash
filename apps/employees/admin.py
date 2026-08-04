from django.contrib import admin

from .models import AttendanceRecord, Employee, PerformanceReview


class AttendanceRecordInline(admin.TabularInline):
    model = AttendanceRecord
    extra = 0
    readonly_fields = ('created_at',)


class PerformanceReviewInline(admin.TabularInline):
    model = PerformanceReview
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_code_display', 'full_name', 'position', 'employment_status', 'hire_date')
    list_filter = ('position', 'employment_status')
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'user__phone_number')
    readonly_fields = ('public_id', 'created_at', 'updated_at')
    ordering = ('user__first_name', 'user__last_name')
    autocomplete_fields = ('user',)
    inlines = [AttendanceRecordInline, PerformanceReviewInline]

    fieldsets = (
        (None, {'fields': ('user', 'position', 'employment_status', 'hire_date', 'termination_date')}),
        ('Schedule', {'fields': ('scheduled_days', 'shift_start_time', 'shift_end_time')}),
        ('Notes', {'fields': ('notes',)}),
        ('Metadata', {'fields': ('created_by', 'public_id', 'created_at', 'updated_at')}),
    )

    def employee_code_display(self, obj):
        return obj.employee_code
    employee_code_display.short_description = 'Employee Code'

    def full_name(self, obj):
        return obj.full_name


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'status', 'clock_in_time', 'clock_out_time')
    list_filter = ('status', 'date')
    search_fields = ('employee__user__first_name', 'employee__user__last_name')
    date_hierarchy = 'date'


@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ('employee', 'review_date', 'rating', 'reviewed_by')
    list_filter = ('rating',)
    search_fields = ('employee__user__first_name', 'employee__user__last_name')
    date_hierarchy = 'review_date'
