"""
Hooks Invoice creation into Booking status changes without touching
apps.bookings -- purely additive, same approach as
apps.inventory.signals. Idempotent: get_or_create_invoice_for_booking
only ever creates one Invoice per booking.
"""
from django.db.models.signals import post_save


def _handle_booking_saved(sender, instance, **kwargs):
    from apps.bookings.models import BookingStatus
    from . import services

    if instance.status == BookingStatus.CONFIRMED:
        services.get_or_create_invoice_for_booking(instance)


def connect():
    from apps.bookings.models import Booking
    post_save.connect(_handle_booking_saved, sender=Booking, dispatch_uid='payments_booking_invoice_hook')
