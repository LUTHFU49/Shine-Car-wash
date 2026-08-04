"""
Hooks the Inventory module into Booking status changes without touching
apps.bookings at all -- purely additive, so Phases 1-7 stay untouched.
Each handler below is idempotent (checked inside apps.inventory.services)
so re-saving a booking already at a given status never double-applies
an effect.
"""
from django.db.models.signals import post_save


def _handle_booking_saved(sender, instance, **kwargs):
    from apps.bookings.models import BookingStatus
    from . import services

    if instance.status == BookingStatus.CONFIRMED:
        services.reserve_stock_for_booking(instance)
    elif instance.status == BookingStatus.COMPLETED:
        services.consume_reserved_stock(instance)
    elif instance.status in (BookingStatus.CANCELLED, BookingStatus.NO_SHOW):
        services.release_reservations_for_booking(instance)


def connect():
    from apps.bookings.models import Booking
    post_save.connect(_handle_booking_saved, sender=Booking, dispatch_uid='inventory_booking_status_hook')
