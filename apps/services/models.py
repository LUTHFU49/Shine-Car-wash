import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

WEEKDAY_CHOICES = [
    ('mon', 'Monday'),
    ('tue', 'Tuesday'),
    ('wed', 'Wednesday'),
    ('thu', 'Thursday'),
    ('fri', 'Friday'),
    ('sat', 'Saturday'),
    ('sun', 'Sunday'),
]
WEEKDAY_CODES = [code for code, _ in WEEKDAY_CHOICES]

# Font Awesome 6 icons curated for a car wash service catalog -- kept as
# a fixed choice list (rather than free text) so the catalog page never
# ends up with a broken/mismatched icon class.
SERVICE_CATEGORY_ICON_CHOICES = [
    ('fa-car', 'Car'),
    ('fa-car-side', 'Car (Side)'),
    ('fa-truck', 'Truck'),
    ('fa-truck-pickup', 'Pickup'),
    ('fa-van-shuttle', 'Van / Shuttle'),
    ('fa-motorcycle', 'Motorcycle'),
    ('fa-bus', 'Bus'),
    ('fa-spray-can-sparkles', 'Detailing'),
    ('fa-soap', 'Soap / Wash'),
    ('fa-droplet', 'Water / Rinse'),
    ('fa-broom', 'Interior Clean'),
    ('fa-brush', 'Polish / Wax'),
]


class ServiceCategory(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    icon = models.CharField(max_length=30, choices=SERVICE_CATEGORY_ICON_CHOICES, default='fa-car')
    display_order = models.PositiveIntegerField(default=0, help_text='Lower numbers appear first in the catalog.')
    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='service_categories_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'services_category'
        ordering = ['display_order', 'name']
        verbose_name_plural = 'Service categories'

    def __str__(self):
        return self.name


class ServiceStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    INACTIVE = 'inactive', 'Inactive'


class Service(models.Model):
    """
    A bookable wash service. Never hard-deleted -- once Bookings/Payments
    exist against a service in later phases, historical records need the
    service to still resolve, hence `status` rather than delete.
    """
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    category = models.ForeignKey(
        ServiceCategory, on_delete=models.PROTECT, related_name='services',
    )

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(1)])
    duration_minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(5)],
        help_text='Estimated time to complete this service, in minutes.',
    )
    status = models.CharField(max_length=10, choices=ServiceStatus.choices, default=ServiceStatus.ACTIVE, db_index=True)

    # Blank = available every day. Otherwise a comma-separated subset of
    # WEEKDAY_CODES, e.g. "sat,sun" for a weekend-only detailing service.
    available_days = models.CharField(max_length=50, blank=True)

    image = models.ImageField(upload_to='service_photos/%Y/%m/', blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='services_created',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'services_service'
        ordering = ['category__display_order', 'name']
        indexes = [models.Index(fields=['status'])]

    def __str__(self):
        return f'{self.name} ({self.category.name})'

    @property
    def available_days_list(self):
        if not self.available_days:
            return list(WEEKDAY_CODES)
        return [code.strip() for code in self.available_days.split(',') if code.strip()]

    @property
    def available_days_display(self):
        if not self.available_days:
            return 'Every day'
        codes = self.available_days_list
        labels = dict(WEEKDAY_CHOICES)
        return ', '.join(labels.get(code, code) for code in codes)

    def is_available_today(self):
        if self.status != ServiceStatus.ACTIVE:
            return False
        today_code = WEEKDAY_CODES[timezone.localtime().weekday()]
        return today_code in self.available_days_list

    @property
    def duration_display(self):
        hours, minutes = divmod(self.duration_minutes, 60)
        if hours and minutes:
            return f'{hours}h {minutes}m'
        if hours:
            return f'{hours}h'
        return f'{minutes}m'
