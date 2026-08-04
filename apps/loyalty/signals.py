"""
Hooks loyalty into Booking status changes without touching
apps.bookings at all -- the same additive post_save signal pattern
apps.inventory, apps.payments, and apps.notifications already use.
Connected from apps.loyalty's AppConfig.ready(), which Django calls
after apps.payments' (loyalty comes later in INSTALLED_APPS), so by
the time apply_tier_discount runs on CONFIRMED, the invoice this
booking's Payments signal handler creates already exists.
"""
from django.db.models.signals import post_save


def _handle_booking_saved(sender, instance, **kwargs):
    from apps.bookings.models import BookingStatus
    from . import services

    if instance.status == BookingStatus.CONFIRMED:
        services.apply_tier_discount(instance)
    elif instance.status == BookingStatus.COMPLETED:
        services.handle_booking_completed(instance)


def connect():
    from apps.bookings.models import Booking
    post_save.connect(_handle_booking_saved, sender=Booking, dispatch_uid='loyalty_booking_lifecycle_hook')
