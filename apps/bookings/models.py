import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.services.models import WEEKDAY_CODES


class BookingType(models.TextChoices):
    ONLINE = 'online', 'Online Booking'
    WALK_IN = 'walk_in', 'Walk-in'


class BookingStatus(models.TextChoices):
    PENDING = 'pending', 'Pending Approval'
    CONFIRMED = 'confirmed', 'Confirmed'
    IN_QUEUE = 'in_queue', 'In Queue'
    IN_PROGRESS = 'in_progress', 'Washing'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'
    NO_SHOW = 'no_show', 'No Show'


# Which status transitions are legal. Enforced in Booking.transition_to()
# so a booking can never jump from, say, Completed back to Pending
# through a stray POST request.
ALLOWED_TRANSITIONS = {
    BookingStatus.PENDING: {BookingStatus.CONFIRMED, BookingStatus.CANCELLED},
    BookingStatus.CONFIRMED: {BookingStatus.IN_QUEUE, BookingStatus.CANCELLED},
    BookingStatus.IN_QUEUE: {BookingStatus.IN_PROGRESS, BookingStatus.CANCELLED, BookingStatus.NO_SHOW},
    BookingStatus.IN_PROGRESS: {BookingStatus.COMPLETED, BookingStatus.CANCELLED},
    BookingStatus.COMPLETED: set(),
    BookingStatus.CANCELLED: set(),
    BookingStatus.NO_SHOW: set(),
}

# Terminal statuses can never be rescheduled or re-cancelled.
TERMINAL_STATUSES = {BookingStatus.COMPLETED, BookingStatus.CANCELLED, BookingStatus.NO_SHOW}


class Booking(models.Model):

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    customer = models.ForeignKey('customers.Customer', on_delete=models.CASCADE, related_name='bookings')
    vehicle = models.ForeignKey('vehicles.Vehicle', on_delete=models.PROTECT, related_name='bookings')
    service = models.ForeignKey('services.Service', on_delete=models.PROTECT, related_name='bookings')

    booking_type = models.CharField(max_length=10, choices=BookingType.choices, default=BookingType.ONLINE)
    status = models.CharField(max_length=12, choices=BookingStatus.choices, default=BookingStatus.PENDING, db_index=True)

    assigned_employee = models.ForeignKey(
        'employees.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_bookings',
        help_text='Staff member assigned to carry out this wash.',
    )

    scheduled_date = models.DateField(db_index=True)
    scheduled_time = models.TimeField()

    # Snapshots taken at booking time so a later price/duration change to
    # the Service doesn't retroactively rewrite historical bookings.
    price_at_booking = models.DecimalField(max_digits=10, decimal_places=2)
    duration_minutes_at_booking = models.PositiveIntegerField()

    notes = models.TextField(blank=True, help_text="Customer's notes or special requests.")
    staff_notes = models.TextField(blank=True, help_text='Internal notes -- never shown to the customer.')

    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings_cancelled',
    )
    cancellation_reason = models.CharField(max_length=255, blank=True)

    confirmation_email_sent_at = models.DateTimeField(blank=True, null=True)
    reminder_email_sent_at = models.DateTimeField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bookings_created',
        help_text='Staff member who created this booking, if a walk-in. Null for online self-bookings.',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bookings_booking'
        ordering = ['scheduled_date', 'scheduled_time']
        indexes = [
            models.Index(fields=['scheduled_date', 'status']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f'{self.booking_code} — {self.vehicle.license_plate} @ {self.scheduled_date} {self.scheduled_time}'

    @property
    def booking_code(self):
        return f'BK-{self.pk:06d}' if self.pk else 'BK-PENDING'

    @property
    def is_terminal(self):
        return self.status in TERMINAL_STATUSES

    @property
    def is_past(self):
        now = timezone.localtime()
        return self.scheduled_date < now.date() or (
            self.scheduled_date == now.date() and self.scheduled_time < now.time()
        )

    def can_transition_to(self, new_status):
        return new_status in ALLOWED_TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status, extra_fields=None):
        if not self.can_transition_to(new_status):
            raise ValidationError(
                f'Cannot move a booking from "{self.get_status_display()}" to '
                f'"{dict(BookingStatus.choices).get(new_status, new_status)}".'
            )
        self.status = new_status
        fields_to_save = ['status', 'updated_at']
        if new_status == BookingStatus.CANCELLED:
            self.cancelled_at = timezone.now()
            fields_to_save.append('cancelled_at')
        if extra_fields:
            fields_to_save.extend(extra_fields)
        self.save(update_fields=fields_to_save)

    def clean(self):
        errors = {}
        now = timezone.localtime()

        if self.scheduled_date and self.scheduled_date < now.date():
            errors['scheduled_date'] = 'You cannot book a date in the past.'
        elif self.scheduled_date == now.date() and self.scheduled_time and self.scheduled_time < now.time():
            errors['scheduled_time'] = 'You cannot book a time slot that has already passed today.'

        if self.scheduled_time:
            from django.conf import settings as dj_settings
            start_hour = getattr(dj_settings, 'BUSINESS_HOURS_START_HOUR', 8)
            end_hour = getattr(dj_settings, 'BUSINESS_HOURS_END_HOUR', 18)
            if not (start_hour <= self.scheduled_time.hour < end_hour):
                errors['scheduled_time'] = f'Choose a time between {start_hour:02d}:00 and {end_hour:02d}:00.'

        if self.scheduled_date and self.service_id and self.service:
            weekday_code = WEEKDAY_CODES[self.scheduled_date.weekday()]
            if weekday_code not in self.service.available_days_list:
                errors['scheduled_date'] = f'{self.service.name} is not available on {self.scheduled_date.strftime("%A")}s.'

        if self.vehicle_id and self.scheduled_date and self.scheduled_time:
            clashing = Booking.objects.filter(
                vehicle_id=self.vehicle_id,
                scheduled_date=self.scheduled_date,
                scheduled_time=self.scheduled_time,
            ).exclude(status__in=[BookingStatus.CANCELLED]).exclude(pk=self.pk)
            if clashing.exists():
                errors['scheduled_time'] = 'This vehicle already has a booking at that date and time.'

        if errors:
            raise ValidationError(errors)
