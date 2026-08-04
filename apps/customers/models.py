import uuid

from django.conf import settings
from django.db import models

from apps.accounts.models import phone_validator


class Customer(models.Model):
    """
    A customer record, managed by staff (Super Admin / Manager / Cashier).

    Two ways a Customer row comes to exist:
      1. Self-registration: a User with role=Customer signs up through
         the public site -- a Customer profile is auto-created and linked
         via `user` (see apps.accounts.signals).
      2. Walk-in: staff register a customer at the counter who has no
         login account at all (`user` is null).

    Either way, staff manage every customer from one place.
    """
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='customer_profile',
        help_text='Set automatically if this customer has a ShineHub login account.',
    )

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=17, validators=[phone_validator], unique=True)

    date_of_birth = models.DateField(blank=True, null=True)
    address = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True, help_text='Internal staff notes -- never shown to the customer.')

    is_active = models.BooleanField(default=True, db_index=True)
    deactivated_at = models.DateTimeField(blank=True, null=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='customers_registered',
        help_text='The staff member who registered this customer, if a walk-in.',
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customers_customer'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f'{self.full_name} ({self.customer_code})'

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def customer_code(self):
        return f'CUST-{self.pk:06d}' if self.pk else 'CUST-PENDING'

    @property
    def is_linked_account(self):
        return self.user_id is not None
