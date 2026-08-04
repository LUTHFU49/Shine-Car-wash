import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.services.models import WEEKDAY_CHOICES, WEEKDAY_CODES


class EmployeePosition(models.TextChoices):
    WASHER = 'washer', 'Washer'
    DETAILER = 'detailer', 'Detailer'
    ATTENDANT = 'attendant', 'Attendant'
    SUPERVISOR = 'supervisor', 'Supervisor'
    CASHIER_TRAINEE = 'cashier_trainee', 'Cashier Trainee'
    OTHER = 'other', 'Other'


class EmploymentStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    ON_LEAVE = 'on_leave', 'On Leave'
    TERMINATED = 'terminated', 'Terminated'


class Employee(models.Model):
    """
    HR profile for a User with role=Employee. Every Employee has exactly
    one linked User account (created together during onboarding -- see
    apps.employees.views.employee_create_view); the login/auth side lives
    on User, the HR side lives here.
    """
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='employee_profile',
    )

    position = models.CharField(max_length=20, choices=EmployeePosition.choices, default=EmployeePosition.WASHER)
    employment_status = models.CharField(max_length=12, choices=EmploymentStatus.choices, default=EmploymentStatus.ACTIVE, db_index=True)
    hire_date = models.DateField(default=timezone.localdate)
    termination_date = models.DateField(blank=True, null=True)

    # Weekly recurring shift -- mirrors Service.available_days from the
    # Services phase (same WEEKDAY_CODES) for a consistent pattern across
    # the project rather than inventing a second day-of-week convention.
    scheduled_days = models.CharField(max_length=50, blank=True, help_text='Blank = no fixed schedule set yet.')
    shift_start_time = models.TimeField(blank=True, null=True)
    shift_end_time = models.TimeField(blank=True, null=True)

    notes = models.TextField(blank=True, help_text='Internal HR notes -- never shown to the employee.')

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees_onboarded',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'employees_employee'
        ordering = ['user__first_name', 'user__last_name']
        indexes = [models.Index(fields=['employment_status'])]

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} ({self.employee_code})'

    @property
    def employee_code(self):
        return f'EMP-{self.pk:06d}' if self.pk else 'EMP-PENDING'

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def scheduled_days_list(self):
        if not self.scheduled_days:
            return []
        return [code.strip() for code in self.scheduled_days.split(',') if code.strip()]

    @property
    def scheduled_days_display(self):
        if not self.scheduled_days:
            return 'Not set'
        labels = dict(WEEKDAY_CHOICES)
        return ', '.join(labels.get(code, code) for code in self.scheduled_days_list)

    def is_scheduled_today(self):
        if self.employment_status != EmploymentStatus.ACTIVE:
            return False
        today_code = WEEKDAY_CODES[timezone.localdate().weekday()]
        return today_code in self.scheduled_days_list


class AttendanceStatus(models.TextChoices):
    PRESENT = 'present', 'Present'
    LATE = 'late', 'Late'
    ABSENT = 'absent', 'Absent'
    ON_LEAVE = 'on_leave', 'On Leave'


class AttendanceRecord(models.Model):
    """One row per employee per day. Recorded by staff (clock-in/out are
    entered manually rather than via a physical time clock device, which
    is out of scope for this system)."""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.localdate, db_index=True)
    status = models.CharField(max_length=10, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    clock_in_time = models.TimeField(blank=True, null=True)
    clock_out_time = models.TimeField(blank=True, null=True)
    notes = models.CharField(max_length=255, blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='attendance_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'employees_attendance_record'
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(fields=['employee', 'date'], name='unique_attendance_per_employee_per_day'),
        ]

    def __str__(self):
        return f'{self.employee.full_name} — {self.date} ({self.get_status_display()})'


class PerformanceReview(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='performance_reviews')
    review_date = models.DateField(default=timezone.localdate)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comments = models.TextField(blank=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='performance_reviews_given',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'employees_performance_review'
        ordering = ['-review_date']

    def __str__(self):
        return f'{self.employee.full_name} — {self.rating}/5 on {self.review_date}'
