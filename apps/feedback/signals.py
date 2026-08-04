"""
Sends a "how was your wash?" review request the moment a booking is
completed -- the same non-invasive post_save hook on Booking that
Phases 8, 9, 11, and 13 already use, connected from apps.feedback so
apps.bookings itself is untouched. Idempotent via a (recipient, url,
title) notification check, same pattern Phase 11 established.
"""
from django.db.models.signals import post_save
from django.urls import reverse

TITLE_REVIEW_REQUEST = 'How was your wash?'


def _handle_booking_saved(sender, instance, **kwargs):
    from apps.bookings.models import BookingStatus
    from apps.notifications.models import Notification, NotificationLevel
    from apps.notifications.utils import notify
    from apps.accounts.emails import send_branded_email

    booking = instance
    if booking.status != BookingStatus.COMPLETED:
        return

    customer_user = getattr(booking.customer, 'user', None)
    if customer_user is None:
        return

    booking_url = reverse('bookings:my_detail', args=[booking.public_id])
    already_sent = Notification.objects.filter(recipient=customer_user, url=booking_url, title=TITLE_REVIEW_REQUEST).exists()
    if already_sent:
        return

    notify(
        customer_user, title=TITLE_REVIEW_REQUEST,
        message=f'Tell us how your {booking.service.name} wash went.',
        level=NotificationLevel.INFO, url=booking_url,
    )
    if customer_user.email:
        send_branded_email(
            subject='How was your wash?',
            template_name='review_request_email.html',
            context={'user': customer_user, 'booking': booking},
            to_email=customer_user.email,
        )


def connect():
    from apps.bookings.models import Booking
    post_save.connect(_handle_booking_saved, sender=Booking, dispatch_uid='feedback_review_request_hook')
