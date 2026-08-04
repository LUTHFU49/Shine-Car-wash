import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role
from apps.bookings.models import Booking, BookingStatus
from apps.customers.models import Customer
from apps.services.models import Service, ServiceCategory
from apps.vehicles.models import Vehicle

from . import services
from .models import (
    InventoryCategory, InventoryItem, ItemBatch, ServiceInventoryRequirement,
    StockMovement, StockReservation,
)

User = get_user_model()


def make_staff_user(role=Role.MANAGER, username='invstaff'):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass1!', role=role,
    )
    user.is_email_verified = True
    user.save()
    return user


def make_customer_with_vehicle(username='invcust', phone='0722000001', plate='KDC 900A'):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass1!', role=Role.CUSTOMER,
        first_name='Inv', last_name='Customer', phone_number=phone,
    )
    customer = Customer.objects.get(user=user)
    vehicle = Vehicle.objects.create(customer=customer, license_plate=plate, make='Toyota', model='Vitz', year=2019, color='White')
    return user, customer, vehicle


def make_item(name='Car Shampoo', current_stock=20, reorder_level=5, track_expiry=False):
    category = InventoryCategory.objects.create(name=f'{name} Category')
    return InventoryItem.objects.create(
        category=category, name=name, current_stock=current_stock, reorder_level=reorder_level, track_expiry=track_expiry,
    )


def make_booking(customer, vehicle, service):
    booking = Booking.objects.create(
        customer=customer, vehicle=vehicle, service=service,
        scheduled_date=timezone.localdate() + datetime.timedelta(days=1), scheduled_time=datetime.time(9, 0),
        price_at_booking=service.price, duration_minutes_at_booking=service.duration_minutes,
    )
    return booking


class StockReservationTests(TestCase):
    """
    Stock reservations are the highest-risk logic in this app: getting
    them wrong means either overselling stock (two bookings both think
    they have the last unit) or permanently locking stock that was
    never actually used.
    """

    def setUp(self):
        _, self.customer, self.vehicle = make_customer_with_vehicle()
        category = ServiceCategory.objects.create(name='Inv Test Services')
        self.service = Service.objects.create(category=category, name='Full Valet', price=1500, duration_minutes=60)
        self.item = make_item(current_stock=20)
        ServiceInventoryRequirement.objects.create(service=self.service, item=self.item, quantity_required=3)
        self.booking = make_booking(self.customer, self.vehicle, self.service)

    def test_confirming_booking_reserves_stock(self):
        self.booking.status = BookingStatus.CONFIRMED
        self.booking.save()
        self.item.refresh_from_db()
        self.assertEqual(self.item.reserved_stock, 3)
        self.assertEqual(StockReservation.objects.filter(booking=self.booking).count(), 1)

    def test_reservation_is_idempotent_on_resave(self):
        self.booking.status = BookingStatus.CONFIRMED
        self.booking.save()
        services.reserve_stock_for_booking(self.booking)  # simulate a re-save/re-trigger
        self.item.refresh_from_db()
        self.assertEqual(self.item.reserved_stock, 3)  # not 6
        self.assertEqual(StockReservation.objects.filter(booking=self.booking).count(), 1)

    def test_completing_booking_consumes_reservation(self):
        self.booking.status = BookingStatus.CONFIRMED
        self.booking.save()
        services.consume_reserved_stock(self.booking)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, 17)  # 20 - 3
        self.assertEqual(self.item.reserved_stock, 0)
        reservation = StockReservation.objects.get(booking=self.booking)
        self.assertEqual(reservation.status, StockReservation.ReservationStatus.CONSUMED)

    def test_consuming_twice_does_not_double_deduct(self):
        self.booking.status = BookingStatus.CONFIRMED
        self.booking.save()
        services.consume_reserved_stock(self.booking)
        services.consume_reserved_stock(self.booking)  # simulate a re-save
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, 17)  # still 17, not 14

    def test_cancelling_booking_releases_reservation(self):
        self.booking.status = BookingStatus.CONFIRMED
        self.booking.save()
        services.release_reservations_for_booking(self.booking)
        self.item.refresh_from_db()
        self.assertEqual(self.item.reserved_stock, 0)
        self.assertEqual(self.item.current_stock, 20)  # never actually deducted
        reservation = StockReservation.objects.get(booking=self.booking)
        self.assertEqual(reservation.status, StockReservation.ReservationStatus.RELEASED)

    def test_service_with_no_requirements_does_not_reserve_anything(self):
        plain_category = ServiceCategory.objects.create(name='No Requirements Category')
        plain_service = Service.objects.create(category=plain_category, name='Plain Wash', price=300, duration_minutes=20)
        plain_booking = make_booking(self.customer, self.vehicle, plain_service)
        plain_booking.status = BookingStatus.CONFIRMED
        plain_booking.save()
        self.assertEqual(StockReservation.objects.filter(booking=plain_booking).count(), 0)


class FifoBatchConsumptionTests(TestCase):
    """Expiry-tracked items must consume the soonest-to-expire batch
    first -- getting this backwards means write-offs of nearly-expired
    stock while fresher stock sits reserved for later use."""

    def setUp(self):
        _, self.customer, self.vehicle = make_customer_with_vehicle(username='fifocust', plate='KDC 901A')
        category = ServiceCategory.objects.create(name='Fifo Test Services')
        self.service = Service.objects.create(category=category, name='Wax Treatment', price=2000, duration_minutes=45)
        self.item = make_item(name='Car Wax', current_stock=15, track_expiry=True)
        ServiceInventoryRequirement.objects.create(service=self.service, item=self.item, quantity_required=8)

        today = timezone.localdate()
        self.older_batch = ItemBatch.objects.create(
            item=self.item, quantity_received=10, quantity_remaining=10,
            unit_cost=Decimal('50.00'), expiry_date=today + datetime.timedelta(days=10),
        )
        self.newer_batch = ItemBatch.objects.create(
            item=self.item, quantity_received=5, quantity_remaining=5,
            unit_cost=Decimal('55.00'), expiry_date=today + datetime.timedelta(days=60),
        )

    def test_consumption_takes_from_soonest_expiring_batch_first(self):
        booking = make_booking(self.customer, self.vehicle, self.service)
        booking.status = BookingStatus.CONFIRMED
        booking.save()
        services.consume_reserved_stock(booking)

        self.older_batch.refresh_from_db()
        self.newer_batch.refresh_from_db()
        # 8 needed: all 8 should come from the soon-to-expire batch (had 10),
        # leaving the far-future batch completely untouched.
        self.assertEqual(self.older_batch.quantity_remaining, 2)
        self.assertEqual(self.newer_batch.quantity_remaining, 5)

    def test_consumption_spills_into_next_batch_when_first_is_insufficient(self):
        # Reduce the older batch so 8 units can't come from it alone.
        self.older_batch.quantity_remaining = 3
        self.older_batch.save()

        booking = make_booking(self.customer, self.vehicle, self.service)
        booking.status = BookingStatus.CONFIRMED
        booking.save()
        services.consume_reserved_stock(booking)

        self.older_batch.refresh_from_db()
        self.newer_batch.refresh_from_db()
        self.assertEqual(self.older_batch.quantity_remaining, 0)
        self.assertEqual(self.newer_batch.quantity_remaining, 0)  # 3 + 5 = 8 needed exactly


class StockMovementAuditTrailTests(TestCase):
    """Every reservation/consumption/release must leave a StockMovement
    row -- this is the inventory app's own audit trail, separate from
    the generic AuditLog."""

    def setUp(self):
        _, self.customer, self.vehicle = make_customer_with_vehicle(username='movecust', plate='KDC 902A')
        category = ServiceCategory.objects.create(name='Movement Test Services')
        self.service = Service.objects.create(category=category, name='Interior Clean', price=1200, duration_minutes=40)
        self.item = make_item(name='Vacuum Bags', current_stock=10)
        ServiceInventoryRequirement.objects.create(service=self.service, item=self.item, quantity_required=1)
        self.booking = make_booking(self.customer, self.vehicle, self.service)

    def test_reserve_then_consume_leaves_both_movement_records(self):
        self.booking.status = BookingStatus.CONFIRMED
        self.booking.save()
        services.consume_reserved_stock(self.booking)

        movements = list(StockMovement.objects.filter(booking=self.booking).order_by('created_at'))
        movement_types = [m.movement_type for m in movements]
        self.assertIn(StockMovement.MovementType.BOOKING_RESERVED, movement_types)
        self.assertIn(StockMovement.MovementType.BOOKING_USED, movement_types)
