import random
import string
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class LoyaltyTier(models.Model):
    """A membership level, e.g. Bronze/Silver/Gold/Platinum. A
    customer's tier is recalculated from their lifetime_points every
    time they earn more (see apps.loyalty.services.recalculate_tier) --
    tiers never go down when a customer merely spends points, only
    lifetime_points matters."""
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    name = models.CharField(max_length=50, unique=True)
    minimum_points = models.PositiveIntegerField(help_text='Lifetime points required to reach this tier.')
    discount_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'),
        help_text='Automatic discount applied to every booking for members of this tier.',
    )
    points_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal('1.00'),
        help_text='Multiplies points earned per booking, e.g. 1.5 for 50% bonus points.',
    )
    icon = models.CharField(max_length=30, default='fa-medal')
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='loyalty_tiers_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'loyalty_tier'
        ordering = ['minimum_points']

    def __str__(self):
        return self.name


def _generate_referral_code():
    while True:
        code = 'REF-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not LoyaltyProfile.objects.filter(referral_code=code).exists():
            return code


class LoyaltyProfile(models.Model):
    """One per Customer -- the membership record. Created lazily (see
    apps.loyalty.services.get_or_create_profile) the first time a
    customer's loyalty data is touched, so existing Phase 3 customers
    never needed a migration to backfill this."""
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    customer = models.OneToOneField('customers.Customer', on_delete=models.CASCADE, related_name='loyalty_profile')

    points_balance = models.PositiveIntegerField(default=0, editable=False, help_text='Currently spendable points.')
    lifetime_points = models.PositiveIntegerField(default=0, editable=False, help_text='Total ever earned -- what tier is based on.')
    tier = models.ForeignKey(LoyaltyTier, on_delete=models.PROTECT, null=True, blank=True, related_name='members')
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), editable=False)

    referral_code = models.CharField(max_length=20, unique=True, default=_generate_referral_code, editable=False)
    referred_by = models.ForeignKey(
        'customers.Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals_made',
    )
    referral_bonus_granted = models.BooleanField(
        default=False, editable=False,
        help_text='Whether the referrer has already been rewarded for this customer\'s first booking.',
    )
    last_birthday_reward_year = models.PositiveIntegerField(blank=True, null=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'loyalty_profile'

    def __str__(self):
        return f'Loyalty profile for {self.customer}'


class PointsTransactionType(models.TextChoices):
    EARNED_BOOKING = 'earned_booking', 'Earned (Booking)'
    EARNED_REFERRAL = 'earned_referral', 'Earned (Referral Bonus)'
    EARNED_BIRTHDAY = 'earned_birthday', 'Earned (Birthday Bonus)'
    REDEEMED = 'redeemed', 'Redeemed'
    ADJUSTMENT = 'adjustment', 'Manual Adjustment'


class PointsTransaction(models.Model):
    """Append-only points ledger -- profile.points_balance/lifetime_points
    are denormalized and maintained exclusively by apps.loyalty.services."""
    profile = models.ForeignKey(LoyaltyProfile, on_delete=models.CASCADE, related_name='points_transactions')
    transaction_type = models.CharField(max_length=20, choices=PointsTransactionType.choices, db_index=True)
    points = models.IntegerField(help_text='Always a positive magnitude for EARNED_*; positive for REDEEMED/ADJUSTMENT means deducted.')
    booking = models.ForeignKey('bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='points_transactions')
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'loyalty_points_transaction'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_transaction_type_display()}: {self.points} pts -> {self.profile}'


class WalletTransactionType(models.TextChoices):
    CREDIT_REFERRAL = 'credit_referral', 'Credit (Referral Bonus)'
    CREDIT_PROMOTIONAL = 'credit_promotional', 'Credit (Promotional)'
    CREDIT_MANUAL = 'credit_manual', 'Credit (Manual)'
    DEBIT_PAYMENT = 'debit_payment', 'Debit (Used for Payment)'


class WalletTransaction(models.Model):
    """Append-only wallet ledger -- profile.wallet_balance is
    denormalized and maintained exclusively by apps.loyalty.services."""
    profile = models.ForeignKey(LoyaltyProfile, on_delete=models.CASCADE, related_name='wallet_transactions')
    transaction_type = models.CharField(max_length=20, choices=WalletTransactionType.choices, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    payment = models.ForeignKey('payments.Payment', on_delete=models.SET_NULL, null=True, blank=True, related_name='wallet_transactions')
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'loyalty_wallet_transaction'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_transaction_type_display()}: KSh {self.amount} -> {self.profile}'


class DiscountType(models.TextChoices):
    PERCENTAGE = 'percentage', 'Percentage'
    FIXED_AMOUNT = 'fixed_amount', 'Fixed Amount'


class Coupon(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    code = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=255, blank=True)

    discount_type = models.CharField(max_length=15, choices=DiscountType.choices, default=DiscountType.PERCENTAGE)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    minimum_spend = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    max_uses = models.PositiveIntegerField(blank=True, null=True, help_text='Leave blank for unlimited total uses.')
    times_used = models.PositiveIntegerField(default=0, editable=False)
    max_uses_per_customer = models.PositiveIntegerField(default=1)

    valid_from = models.DateField(default=timezone.localdate)
    valid_until = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='coupons_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'loyalty_coupon'
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    @property
    def is_currently_valid(self):
        today = timezone.localdate()
        if not self.is_active:
            return False
        if today < self.valid_from:
            return False
        if self.valid_until and today > self.valid_until:
            return False
        if self.max_uses is not None and self.times_used >= self.max_uses:
            return False
        return True


class DiscountSource(models.TextChoices):
    TIER = 'tier', 'Membership Tier'
    COUPON = 'coupon', 'Coupon'


class DiscountApplication(models.Model):
    """One row per discount applied to a booking's invoice -- an
    automatic tier discount, a redeemed coupon, or both. This is also
    the project's promotion history: every row here is a promotion
    that actually took effect for a real customer."""
    booking = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE, related_name='discount_applications')
    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT, related_name='discount_applications')
    source = models.CharField(max_length=10, choices=DiscountSource.choices, db_index=True)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name='redemptions')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    applied_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'loyalty_discount_application'
        ordering = ['-applied_at']

    def __str__(self):
        label = self.coupon.code if self.coupon_id else self.get_source_display()
        return f'{label}: KSh {self.discount_amount} on {self.booking.booking_code}'
