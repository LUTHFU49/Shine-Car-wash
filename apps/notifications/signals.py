"""
Hooks in-app notifications onto Booking status changes without
touching apps.bookings at all -- the same additive post_save signal
pattern apps.inventory and apps.payments already use. Each notify()
call here is idempotent against re-saves because it checks for an
existing (recipient, url, title) match first; Notification doesn't
carry a FK back to Booking, so that triple is the practical identity
key for "have I already sent this specific alert for this booking."
"""
from django.db.models.signals import post_save
from django.urls import reverse

from .models import Notification, NotificationLevel
from .utils import notify, notify_roles

TITLE_CONFIRMED = 'Booking confirmed'
TITLE_COMPLETED = 'Wash complete'
TITLE_CANCELLED = 'Booking cancelled'
TITLE_ASSIGNED = 'New assignment'
TITLE_ADMIN_CANCELLED = 'A booking was cancelled'


def _already_sent(user, url, title):
    return Notification.objects.filter(recipient=user, url=url, title=title).exists()


def _handle_booking_saved(sender, instance, **kwargs):
    from apps.bookings.models import BookingStatus

    booking = instance
    customer_user = getattr(booking.customer, 'user', None)
    customer_url = reverse('bookings:my_detail', args=[booking.public_id])

    if booking.status == BookingStatus.CONFIRMED:
        if customer_user and not _already_sent(customer_user, customer_url, TITLE_CONFIRMED):
            notify(
                customer_user, title=TITLE_CONFIRMED,
                message=f'Your {booking.service.name} booking on {booking.scheduled_date} at {booking.scheduled_time} is confirmed.',
                level=NotificationLevel.SUCCESS, url=customer_url,
            )

        if booking.assigned_employee_id:
            employee_user = booking.assigned_employee.user
            assignments_url = reverse('employees:my_assignments')
            if not _already_sent(employee_user, assignments_url, TITLE_ASSIGNED):
                notify(
                    employee_user, title=TITLE_ASSIGNED,
                    message=f'You have been assigned {booking.booking_code} ({booking.service.name}) on {booking.scheduled_date}.',
                    level=NotificationLevel.INFO, url=assignments_url,
                )

    elif booking.status == BookingStatus.COMPLETED:
        if customer_user and not _already_sent(customer_user, customer_url, TITLE_COMPLETED):
            notify(
                customer_user, title=TITLE_COMPLETED,
                message=f'Your {booking.service.name} wash is done -- thanks for choosing us!',
                level=NotificationLevel.SUCCESS, url=customer_url,
            )

    elif booking.status == BookingStatus.CANCELLED:
        if customer_user and not _already_sent(customer_user, customer_url, TITLE_CANCELLED):
            notify(
                customer_user, title=TITLE_CANCELLED,
                message=f'Your {booking.service.name} booking on {booking.scheduled_date} was cancelled.',
                level=NotificationLevel.WARNING, url=customer_url,
            )

        staff_url = reverse('bookings:detail', args=[booking.public_id])
        admin_message = f'{booking.booking_code} for {booking.vehicle.license_plate} was cancelled.'
        already_notified_admins = Notification.objects.filter(
            url=staff_url, title=TITLE_ADMIN_CANCELLED, message=admin_message,
        ).exists()
        if not already_notified_admins:
            from apps.accounts.models import Role
            notify_roles(
                [Role.SUPER_ADMIN, Role.MANAGER], title=TITLE_ADMIN_CANCELLED,
                message=admin_message, level=NotificationLevel.WARNING, url=staff_url,
            )


def connect():
    from apps.bookings.models import Booking
    post_save.connect(_handle_booking_saved, sender=Booking, dispatch_uid='notifications_booking_lifecycle_hook')
