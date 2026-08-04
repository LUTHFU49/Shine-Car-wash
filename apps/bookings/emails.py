"""
Booking-related emails: received (pending approval acknowledgment),
confirmed, cancelled, and reminder. All go through the shared
send_branded_email() helper so failures are logged, not raised, and
never block the request/response cycle.
"""

from apps.accounts.emails import send_branded_email


def _booking_context(booking):
    return {
        'booking': booking,
        'customer': booking.customer,
        'vehicle': booking.vehicle,
        'service': booking.service,
    }


def _recipient_email(booking):
    return booking.customer.email


def send_booking_received_email(booking):
    if not _recipient_email(booking):
        return False
    return send_branded_email(
        subject=f'Booking Received — {booking.booking_code}',
        template_name='booking_received_email.html',
        context=_booking_context(booking),
        to_email=_recipient_email(booking),
    )


def send_booking_confirmed_email(booking):
    if not _recipient_email(booking):
        return False
    return send_branded_email(
        subject=f'Booking Confirmed — {booking.booking_code}',
        template_name='booking_confirmed_email.html',
        context=_booking_context(booking),
        to_email=_recipient_email(booking),
    )


def send_booking_cancelled_email(booking):
    if not _recipient_email(booking):
        return False
    return send_branded_email(
        subject=f'Booking Cancelled — {booking.booking_code}',
        template_name='booking_cancelled_email.html',
        context=_booking_context(booking),
        to_email=_recipient_email(booking),
    )


def send_booking_reminder_email(booking):
    if not _recipient_email(booking):
        return False
    return send_branded_email(
        subject=f'Reminder: Your Wash Tomorrow — {booking.booking_code}',
        template_name='booking_reminder_email.html',
        context=_booking_context(booking),
        to_email=_recipient_email(booking),
    )
