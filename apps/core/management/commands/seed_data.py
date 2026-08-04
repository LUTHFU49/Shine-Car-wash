"""
Generates realistic demo data for local development across every core
app: Users/Employees, Customers, Vehicles, Service categories/Services,
Inventory categories/Suppliers/Items, Loyalty tiers, and Bookings (with
real Invoices + cash Payments for completed ones, via the actual
apps.payments.services layer -- not hand-rolled financial state).

Usage:
    python manage.py seed_data
    python manage.py seed_data --reset
    python manage.py seed_data --customers=500
    python manage.py seed_data --bookings=1000
    python manage.py seed_data --customers=200 --bookings=800 --employees=20

Idempotent by design: every seeded record uses a deterministic natural
key (phone number, license plate, username, name) so re-running the
command without --reset tops up to the requested counts instead of
duplicating rows. Booking counts are checked against how many bookings
already exist for seeded customers, then only the shortfall is created.

--reset deletes previously seeded data ONLY (everything reachable from
the deterministic seed_customer_* / seed_employee_* accounts, plus the
reference data this command owns) -- it never touches unrelated records
a developer created by hand through the UI.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.bookings.models import Booking, BookingStatus, BookingType
from apps.customers.models import Customer
from apps.employees.models import Employee, EmployeePosition, EmploymentStatus
from apps.inventory.models import InventoryCategory, InventoryItem, InventoryUnit, Supplier
from apps.loyalty.models import LoyaltyTier
from apps.payments.services import get_or_create_invoice_for_booking, record_cash_payment
from apps.services.models import Service, ServiceCategory, ServiceStatus
from apps.vehicles.models import Vehicle, VehicleStatus, VehicleType

User = get_user_model()

SEED_PHONE_PREFIX = '07000'       # every seeded customer's phone starts with this
SEED_USERNAME_PREFIX = 'seed_'    # every seeded user account starts with this
SEED_PLATE_PREFIX = 'KDS'         # every seeded vehicle plate starts with this

FIRST_NAMES = [
    'Wanjiku', 'Kamau', 'Achieng', 'Otieno', 'Njeri', 'Mwangi', 'Wafula', 'Nafula',
    'Chebet', 'Kiptoo', 'Wambui', 'Kariuki', 'Auma', 'Odhiambo', 'Naliaka', 'Barasa',
    'Nyambura', 'Kimani', 'Adhiambo', 'Omondi', 'Muthoni', 'Maina', 'Jepkosgei', 'Rotich',
    'Akinyi', 'Owino', 'Nasimiyu', 'Wekesa', 'Waithera', 'Njoroge',
]
LAST_NAMES = [
    'Kamau', 'Otieno', 'Mwangi', 'Wafula', 'Kiptoo', 'Kariuki', 'Odhiambo', 'Barasa',
    'Kimani', 'Omondi', 'Maina', 'Rotich', 'Owino', 'Wekesa', 'Njoroge', 'Cheruiyot',
]
VEHICLE_MAKES_MODELS = [
    ('Toyota', 'Axio'), ('Toyota', 'Prado'), ('Toyota', 'Vitz'), ('Toyota', 'Hilux'),
    ('Nissan', 'X-Trail'), ('Nissan', 'Note'), ('Mazda', 'Demio'), ('Mazda', 'CX-5'),
    ('Subaru', 'Forester'), ('Subaru', 'Impreza'), ('Honda', 'Fit'), ('Honda', 'CR-V'),
    ('Mitsubishi', 'Outlander'), ('Isuzu', 'D-Max'), ('Volkswagen', 'Golf'), ('Mercedes-Benz', 'C-Class'),
]
COLORS = ['White', 'Silver', 'Black', 'Grey', 'Blue', 'Red', 'Maroon', 'Beige']


class Command(BaseCommand):
    help = (
        'Seed realistic demo data (customers, vehicles, employees, services, '
        'inventory, bookings, invoices, payments) for local development. '
        'Idempotent -- safe to re-run. Use --reset to wipe previously seeded data first.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete previously seeded demo data first.')
        parser.add_argument('--customers', type=int, default=40, help='Target number of seeded customers (default: 40).')
        parser.add_argument('--bookings', type=int, default=150, help='Target number of seeded bookings (default: 150).')
        parser.add_argument('--employees', type=int, default=10, help='Target number of seeded employees (default: 10).')

    def handle(self, *args, **options):
        random.seed(42)  # deterministic output across runs, for predictable demos

        if options['reset']:
            self._reset()

        with transaction.atomic():
            admin = self._seed_admin()
            categories = self._seed_service_categories(admin)
            services = self._seed_services(categories, admin)
            self._seed_inventory(admin)
            self._seed_loyalty_tiers(admin)
            employees = self._seed_employees(options['employees'], admin)
            customers = self._seed_customers(options['customers'], admin)
            vehicles = self._seed_vehicles(customers, admin)
            created_bookings = self._seed_bookings(options['bookings'], customers, vehicles, services, employees, admin)

        self.stdout.write(self.style.SUCCESS(
            f'Seed complete. {len(customers)} customers, {len(vehicles)} vehicles, '
            f'{len(employees)} employees, {len(services)} services, '
            f'{created_bookings} new bookings (existing seed bookings topped up to target).'
        ))

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------
    def _reset(self):
        from apps.payments.models import Invoice, Payment

        self.stdout.write('Resetting previously seeded data...')
        seed_customers = Customer.objects.filter(phone_number__startswith=SEED_PHONE_PREFIX)
        seed_bookings = Booking.objects.filter(customer__in=seed_customers)
        Payment.objects.filter(invoice__booking__in=seed_bookings).delete()
        Invoice.objects.filter(booking__in=seed_bookings).delete()
        seed_bookings.delete()
        Vehicle.objects.filter(customer__in=seed_customers).delete()
        seed_customers.delete()
        User.objects.filter(username__startswith=SEED_USERNAME_PREFIX).delete()
        self.stdout.write(self.style.WARNING('Previously seeded customers/vehicles/bookings/employees removed.'))

    # ------------------------------------------------------------------
    # Reference / admin data
    # ------------------------------------------------------------------
    def _seed_admin(self):
        admin, _ = User.objects.get_or_create(
            username=f'{SEED_USERNAME_PREFIX}system',
            defaults={
                'email': 'seed-system@shinehub.local',
                'role': Role.SUPER_ADMIN,
                'is_staff': True,
                'first_name': 'Seed', 'last_name': 'System',
            },
        )
        return admin

    def _seed_service_categories(self, admin):
        data = [
            ('Wash', 'fa-car'),
            ('Detailing', 'fa-spray-can-sparkles'),
            ('Interior Care', 'fa-broom'),
            ('Add-ons', 'fa-star'),
        ]
        categories = []
        for order, (name, icon) in enumerate(data):
            cat, _ = ServiceCategory.objects.get_or_create(
                name=name, defaults={'icon': icon, 'display_order': order, 'created_by': admin},
            )
            categories.append(cat)
        return categories

    def _seed_services(self, categories, admin):
        by_name = {c.name: c for c in categories}
        data = [
            ('Basic Wash', by_name['Wash'], Decimal('500'), 30, 'Exterior wash, tyre shine, quick vacuum.'),
            ('Premium Wash', by_name['Wash'], Decimal('900'), 45, 'Full exterior + interior wipe-down + wax.'),
            ('Full Detailing', by_name['Detailing'], Decimal('2500'), 120, 'Showroom finish, inside and out.'),
            ('Engine Bay Clean', by_name['Detailing'], Decimal('700'), 30, 'Degrease and detail the engine bay.'),
            ('Interior Deep Clean', by_name['Interior Care'], Decimal('1200'), 60, 'Seats, carpets, dashboard, and vents.'),
            ('Seat Shampooing', by_name['Interior Care'], Decimal('1500'), 75, 'Deep shampoo for fabric or leather seats.'),
            ('Wax & Polish', by_name['Add-ons'], Decimal('600'), 30, 'Hand wax and polish for extra shine.'),
            ('Tyre & Rim Shine', by_name['Add-ons'], Decimal('300'), 15, 'Tyre dressing and rim polish.'),
        ]
        services = []
        for name, category, price, duration, description in data:
            svc, _ = Service.objects.get_or_create(
                name=name, category=category,
                defaults={
                    'price': price, 'duration_minutes': duration, 'description': description,
                    'status': ServiceStatus.ACTIVE, 'created_by': admin,
                },
            )
            services.append(svc)
        return services

    def _seed_inventory(self, admin):
        supplier_data = [
            ('CleanChem Supplies Ltd', 'Peter Kioko', '0722100100'),
            ('AutoCare Distributors', 'Grace Wanjala', '0733100200'),
            ('Nairobi Wash Essentials', 'Samuel Otieno', '0711100300'),
        ]
        suppliers = []
        for name, contact, phone in supplier_data:
            sup, _ = Supplier.objects.get_or_create(
                name=name, defaults={'contact_person': contact, 'phone_number': phone, 'created_by': admin},
            )
            suppliers.append(sup)

        cat, _ = InventoryCategory.objects.get_or_create(
            name='Cleaning Supplies', defaults={'icon': 'fa-pump-soap', 'created_by': admin},
        )

        # (name, unit, reorder_level, current_stock, unit_cost) -- a couple are
        # deliberately seeded at/under reorder_level so the dashboard's
        # low-stock activity feed and inventory alerts have real data to show.
        item_data = [
            ('Car Shampoo', InventoryUnit.LITRE, 10, 4, Decimal('450')),
            ('Microfiber Towels', InventoryUnit.PIECE, 20, 55, Decimal('120')),
            ('Tyre Shine Gel', InventoryUnit.BOTTLE, 8, 3, Decimal('380')),
            ('Car Wax', InventoryUnit.BOTTLE, 5, 12, Decimal('900')),
            ('Interior Cleaner', InventoryUnit.BOTTLE, 8, 20, Decimal('550')),
            ('Air Freshener', InventoryUnit.PIECE, 15, 40, Decimal('150')),
            ('Sponges', InventoryUnit.PACK, 10, 25, Decimal('200')),
        ]
        for name, unit, reorder, stock, cost in item_data:
            item, created = InventoryItem.objects.get_or_create(
                name=name, category=cat,
                defaults={
                    'unit': unit, 'reorder_level': reorder, 'current_stock': stock,
                    'average_unit_cost': cost, 'created_by': admin,
                },
            )
            if created and item.is_low_stock:
                InventoryItem.objects.filter(pk=item.pk).update(
                    low_stock_alerted_at=timezone.now() - timedelta(hours=random.randint(1, 48)),
                )

    def _seed_loyalty_tiers(self, admin):
        data = [
            ('Bronze', 0, Decimal('0'), Decimal('1.00'), 'fa-medal'),
            ('Silver', 500, Decimal('5'), Decimal('1.25'), 'fa-award'),
            ('Gold', 1500, Decimal('10'), Decimal('1.5'), 'fa-trophy'),
            ('Platinum', 4000, Decimal('15'), Decimal('2.0'), 'fa-crown'),
        ]
        for order, (name, minimum, discount, multiplier, icon) in enumerate(data):
            LoyaltyTier.objects.get_or_create(
                name=name,
                defaults={
                    'minimum_points': minimum, 'discount_percentage': discount,
                    'points_multiplier': multiplier, 'icon': icon,
                    'display_order': order, 'created_by': admin,
                },
            )

    # ------------------------------------------------------------------
    # Employees
    # ------------------------------------------------------------------
    def _seed_employees(self, target, admin):
        existing = list(Employee.objects.filter(user__username__startswith=SEED_USERNAME_PREFIX))
        positions = list(EmployeePosition.choices)
        employees = list(existing)
        for i in range(len(existing), target):
            first, last = FIRST_NAMES[i % len(FIRST_NAMES)], LAST_NAMES[(i * 3) % len(LAST_NAMES)]
            username = f'{SEED_USERNAME_PREFIX}employee_{i + 1:03d}'
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@shinehub.local', 'first_name': first, 'last_name': last,
                    'role': Role.EMPLOYEE, 'phone_number': f'0721{i:06d}',
                },
            )
            if created:
                user.set_password('SeedPass123!')
                user.save(update_fields=['password'])
            position = positions[i % len(positions)][0]
            employee, _ = Employee.objects.get_or_create(
                user=user,
                defaults={
                    'position': position, 'employment_status': EmploymentStatus.ACTIVE,
                    'hire_date': timezone.localdate() - timedelta(days=random.randint(30, 900)),
                },
            )
            employees.append(employee)
        return employees

    # ------------------------------------------------------------------
    # Customers + Vehicles
    # ------------------------------------------------------------------
    def _seed_customers(self, target, admin):
        existing = list(Customer.objects.filter(phone_number__startswith=SEED_PHONE_PREFIX))
        customers = list(existing)
        for i in range(len(existing), target):
            first, last = FIRST_NAMES[i % len(FIRST_NAMES)], LAST_NAMES[(i * 7) % len(LAST_NAMES)]
            phone = f'{SEED_PHONE_PREFIX}{i:04d}'
            customer, _ = Customer.objects.get_or_create(
                phone_number=phone,
                defaults={
                    'first_name': first, 'last_name': last,
                    'email': f'{first.lower()}.{last.lower()}{i}@example.com',
                    'created_by': admin,
                },
            )
            customers.append(customer)
            # Backdate created_at for a realistic signup spread over the last ~120 days
            # (auto_now_add ignores a value passed at creation, so update it after).
            Customer.objects.filter(pk=customer.pk).update(
                created_at=timezone.now() - timedelta(days=random.randint(0, 120), hours=random.randint(0, 23)),
            )
        return customers

    def _seed_vehicles(self, customers, admin):
        by_customer = {}
        for v in Vehicle.objects.filter(license_plate__startswith=SEED_PLATE_PREFIX).select_related('customer'):
            by_customer.setdefault(v.customer_id, []).append(v)

        vehicles = [v for vs in by_customer.values() for v in vs]
        existing_plates = {v.license_plate for v in vehicles}
        idx = len(vehicles)  # continue numbering after whatever already exists, never restart at 0
        for customer in customers:
            if customer.pk in by_customer:
                continue
            plate = f'{SEED_PLATE_PREFIX} {100 + idx}{chr(65 + (idx % 26))}'
            while plate in existing_plates:
                idx += 1
                plate = f'{SEED_PLATE_PREFIX} {100 + idx}{chr(65 + (idx % 26))}'
            idx += 1
            make, model = VEHICLE_MAKES_MODELS[idx % len(VEHICLE_MAKES_MODELS)]
            vehicle_type = (
                VehicleType.SUV if 'X-Trail' in model or 'Prado' in model or 'CR-V' in model or 'Forester' in model or 'Outlander' in model
                else VehicleType.PICKUP if model in ('Hilux', 'D-Max')
                else VehicleType.HATCHBACK if model in ('Vitz', 'Note', 'Demio', 'Fit', 'Golf')
                else VehicleType.SEDAN
            )
            vehicle = Vehicle.objects.create(
                customer=customer, license_plate=plate, make=make, model=model,
                year=random.randint(2008, 2025), color=random.choice(COLORS),
                vehicle_type=vehicle_type, status=VehicleStatus.ACTIVE, created_by=admin,
            )
            vehicles.append(vehicle)
        return vehicles

    # ------------------------------------------------------------------
    # Bookings (+ real invoices/payments for completed ones)
    # ------------------------------------------------------------------
    def _seed_bookings(self, target, customers, vehicles, services, employees, admin):
        seed_customer_ids = [c.pk for c in customers]
        already = Booking.objects.filter(customer_id__in=seed_customer_ids).count()
        to_create = max(target - already, 0)
        if not to_create or not vehicles:
            return 0

        # Weighted so most historical bookings are completed (realistic revenue
        # history), with a healthy mix of everything else still in flight.
        status_weights = [
            (BookingStatus.COMPLETED, 55),
            (BookingStatus.CONFIRMED, 10),
            (BookingStatus.PENDING, 10),
            (BookingStatus.IN_QUEUE, 8),
            (BookingStatus.IN_PROGRESS, 7),
            (BookingStatus.CANCELLED, 7),
            (BookingStatus.NO_SHOW, 3),
        ]
        statuses = [s for s, _ in status_weights]
        weights = [w for _, w in status_weights]

        created = 0
        for i in range(to_create):
            vehicle = random.choice(vehicles)
            customer = vehicle.customer
            service = random.choice(services)
            target_status = random.choices(statuses, weights=weights, k=1)[0]

            # Completed/cancelled/no-show bookings are historical; everything
            # else is upcoming, so the dashboard's "today"/"queue" views have
            # real near-term data too.
            if target_status in (BookingStatus.COMPLETED, BookingStatus.CANCELLED, BookingStatus.NO_SHOW):
                scheduled_date = timezone.localdate() - timedelta(days=random.randint(1, 90))
            else:
                scheduled_date = timezone.localdate() + timedelta(days=random.randint(0, 5))

            booking = Booking.objects.create(
                customer=customer, vehicle=vehicle, service=service,
                booking_type=random.choice([BookingType.ONLINE, BookingType.WALK_IN]),
                scheduled_date=scheduled_date,
                scheduled_time=random.choice(['08:00', '09:30', '11:00', '13:00', '14:30', '16:00']),
                price_at_booking=service.price, duration_minutes_at_booking=service.duration_minutes,
                assigned_employee=random.choice(employees) if employees and target_status != BookingStatus.PENDING else None,
                created_by=admin if random.random() < 0.4 else None,
            )
            # Backdate created_at to roughly track the scheduled date, so the
            # dashboard's period-over-period deltas see a realistic spread.
            backdate_days = (timezone.localdate() - scheduled_date).days
            Booking.objects.filter(pk=booking.pk).update(
                created_at=timezone.now() - timedelta(days=max(backdate_days, 0), hours=random.randint(0, 20)),
            )
            booking.refresh_from_db()

            self._advance_booking(booking, target_status, admin)
            created += 1

        return created

    def _advance_booking(self, booking, target_status, admin):
        """Walk a booking through its real transition_to() chain so signals
        (invoice creation) fire the same way they do through the UI, then
        record a real cash payment for completed ones via the payments
        service layer -- not hand-set financial fields."""
        path = {
            BookingStatus.PENDING: [],
            BookingStatus.CONFIRMED: [BookingStatus.CONFIRMED],
            BookingStatus.IN_QUEUE: [BookingStatus.CONFIRMED, BookingStatus.IN_QUEUE],
            BookingStatus.IN_PROGRESS: [BookingStatus.CONFIRMED, BookingStatus.IN_QUEUE, BookingStatus.IN_PROGRESS],
            BookingStatus.COMPLETED: [
                BookingStatus.CONFIRMED, BookingStatus.IN_QUEUE, BookingStatus.IN_PROGRESS, BookingStatus.COMPLETED,
            ],
            BookingStatus.CANCELLED: [BookingStatus.CANCELLED],
            BookingStatus.NO_SHOW: [BookingStatus.CONFIRMED, BookingStatus.IN_QUEUE, BookingStatus.NO_SHOW],
        }[target_status]

        for step in path:
            booking.transition_to(step)

        if target_status == BookingStatus.COMPLETED:
            invoice = get_or_create_invoice_for_booking(booking)
            record_cash_payment(invoice, invoice.total_amount, admin, notes='Seed data payment')
