import uuid
from datetime import date

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class VehicleType(models.TextChoices):
    SEDAN = 'sedan', 'Sedan'
    SUV = 'suv', 'SUV'
    HATCHBACK = 'hatchback', 'Hatchback'
    PICKUP = 'pickup', 'Pickup Truck'
    VAN = 'van', 'Van / Minibus'
    TRUCK = 'truck', 'Truck'
    MOTORCYCLE = 'motorcycle', 'Motorcycle'
    BUS = 'bus', 'Bus'
    OTHER = 'other', 'Other'


class VehicleStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    SOLD = 'sold', 'Sold / Transferred'
    INACTIVE = 'inactive', 'Inactive'


class Vehicle(models.Model):
    """
    A vehicle belongs to exactly one Customer, but a Customer can have
    many vehicles (see Customer.vehicles related_name below). Vehicles
    are never hard-deleted -- once bookings/payments exist against a
    vehicle in later phases, its history needs to survive even after the
    customer sells the car or stops using it, hence `status` rather than
    a simple delete.
    """
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.CASCADE, related_name='vehicles',
    )

    license_plate = models.CharField(max_length=12, unique=True, db_index=True)
    make = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    year = models.PositiveIntegerField(
        validators=[MinValueValidator(1980), MaxValueValidator(date.today().year + 1)],
    )
    color = models.CharField(max_length=30)
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, default=VehicleType.SEDAN)
    status = models.CharField(max_length=10, choices=VehicleStatus.choices, default=VehicleStatus.ACTIVE, db_index=True)

    photo = models.ImageField(upload_to='vehicle_photos/%Y/%m/', blank=True, null=True)
    notes = models.TextField(blank=True, help_text='Internal staff notes -- never shown to the customer.')

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vehicles_registered',
        help_text='Staff member who registered this vehicle, if not self-registered by the customer.',
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vehicles_vehicle'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['make', 'model']),
        ]

    def __str__(self):
        return f'{self.license_plate} — {self.make} {self.model}'

    @property
    def display_name(self):
        return f'{self.year} {self.make} {self.model}'

    @property
    def is_self_registered(self):
        return self.created_by_id is None
