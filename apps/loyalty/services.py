"""
All loyalty-affecting logic lives here, same rationale as
apps.inventory.services and apps.payments.services: the denormalized
fields on LoyaltyProfile (points_balance, lifetime_points,
wallet_balance, tier, referral_bonus_granted) must never drift from
their ledgers (PointsTransaction, WalletTransaction) no matter which
caller -- a signal, a view, or the birthday management command --
triggers the change.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from .models import (
    Coupon, DiscountApplication, DiscountSource, DiscountType, LoyaltyProfile,
    LoyaltyTier, PointsTransaction, PointsTransactionType, WalletTransaction,
    WalletTransactionType,
)


def get_or_create_profile(customer):
    profile, _ = LoyaltyProfile.objects.get_or_create(customer=customer)
    return profile


# ============================================================
# Tiers
# ============================================================

def recalculate_tier(profile):
    """Finds the highest tier the customer's lifetime_points now
    qualifies for and updates profile.tier if it changed, notifying
    them on an upgrade. Never downgrades -- lifetime_points only grows."""
    eligible_tier = (
        LoyaltyTier.objects.filter(is_active=True, minimum_points__lte=profile.lifetime_points)
        .order_by('-minimum_points').first()
    )
    if eligible_tier and eligible_tier.id != profile.tier_id:
        is_upgrade = profile.tier is None or eligible_tier.minimum_points > profile.tier.minimum_points
        LoyaltyProfile.objects.filter(pk=profile.pk).update(tier=eligible_tier)
        profile.tier = eligible_tier
        if is_upgrade:
            from apps.notifications.utils import notify
            from apps.notifications.models import NotificationLevel
            notify(
                profile.customer.user, title=f'Welcome to {eligible_tier.name}!',
                message=f'You\'ve reached {eligible_tier.name} status with {profile.lifetime_points} lifetime points.',
                level=NotificationLevel.SUCCESS, url=reverse('loyalty:my_dashboard'),
            )
    return profile


# ============================================================
# Points
# ============================================================

def award_points(profile, points, transaction_type, booking=None, notes=''):
    if points <= 0:
        return profile
    with transaction.atomic():
        PointsTransaction.objects.create(
            profile=profile, transaction_type=transaction_type, points=points, booking=booking, notes=notes,
        )
        LoyaltyProfile.objects.filter(pk=profile.pk).update(
            points_balance=F('points_balance') + points,
            lifetime_points=F('lifetime_points') + points,
        )
    profile.refresh_from_db()
    recalculate_tier(profile)
    return profile


def redeem_points(profile, points, notes=''):
    if points <= 0:
        raise ValidationError('Points to redeem must be greater than zero.')
    if points > profile.points_balance:
        raise ValidationError('Not enough points available.')
    with transaction.atomic():
        PointsTransaction.objects.create(
            profile=profile, transaction_type=PointsTransactionType.REDEEMED, points=points, notes=notes,
        )
        LoyaltyProfile.objects.filter(pk=profile.pk).update(points_balance=F('points_balance') - points)
    profile.refresh_from_db()
    return profile


def points_for_booking(booking, tier):
    multiplier = tier.points_multiplier if tier else Decimal('1.00')
    base_points = (booking.price_at_booking / Decimal('100')) * settings.LOYALTY_POINTS_PER_100_KSH
    return int(base_points * multiplier)


# ============================================================
# Wallet
# ============================================================

def credit_wallet(profile, amount, transaction_type, notes=''):
    if amount <= 0:
        return profile
    with transaction.atomic():
        WalletTransaction.objects.create(profile=profile, transaction_type=transaction_type, amount=amount, notes=notes)
        LoyaltyProfile.objects.filter(pk=profile.pk).update(wallet_balance=F('wallet_balance') + amount)
    profile.refresh_from_db()
    return profile


def pay_with_wallet(invoice, profile, amount, user):
    """Debits the customer's wallet and records a Payment against the
    invoice via apps.payments.services.record_wallet_payment -- the
    wallet balance and the Payment/Invoice ledger move together in one
    transaction so they can never disagree."""
    if amount <= 0:
        raise ValidationError('Amount must be greater than zero.')
    if amount > profile.wallet_balance:
        raise ValidationError('Not enough wallet balance.')
    if amount > invoice.balance:
        raise ValidationError(f'Amount exceeds the outstanding balance of KSh {invoice.balance:,.2f}.')

    from apps.payments import services as payment_services

    with transaction.atomic():
        payment = payment_services.record_wallet_payment(invoice, amount, user, notes='Paid from loyalty wallet')
        WalletTransaction.objects.create(
            profile=profile, transaction_type=WalletTransactionType.DEBIT_PAYMENT,
            amount=amount, payment=payment, notes=f'Payment for {invoice.booking.booking_code}',
        )
        LoyaltyProfile.objects.filter(pk=profile.pk).update(wallet_balance=F('wallet_balance') - amount)

    profile.refresh_from_db()
    return payment


# ============================================================
# Discounts: automatic tier discount + coupon redemption
# ============================================================

def apply_tier_discount(booking):
    """Idempotent: only ever applies once per booking (checked via
    DiscountApplication, since Invoice doesn't track its own discount
    history). Called from the CONFIRMED signal, after
    apps.payments has already created the invoice."""
    invoice = getattr(booking, 'invoice', None)
    if invoice is None:
        return None
    if DiscountApplication.objects.filter(booking=booking, source=DiscountSource.TIER).exists():
        return None

    profile = get_or_create_profile(booking.customer)
    if not profile.tier or profile.tier.discount_percentage <= 0:
        return None

    discount_amount = (invoice.total_amount * profile.tier.discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
    if discount_amount <= 0:
        return None

    from apps.payments import services as payment_services
    with transaction.atomic():
        payment_services.apply_discount(invoice, discount_amount, reason=f'{profile.tier.name} tier discount')
        application = DiscountApplication.objects.create(
            booking=booking, customer=booking.customer, source=DiscountSource.TIER, discount_amount=discount_amount,
        )
    return application


def validate_and_apply_coupon(booking, code, user):
    invoice = getattr(booking, 'invoice', None)
    if invoice is None:
        raise ValidationError('This booking does not have an invoice yet.')

    try:
        coupon = Coupon.objects.get(code__iexact=code.strip())
    except Coupon.DoesNotExist:
        raise ValidationError('That coupon code was not found.')

    if not coupon.is_currently_valid:
        raise ValidationError('That coupon is no longer valid.')
    if invoice.subtotal < coupon.minimum_spend:
        raise ValidationError(f'This coupon requires a minimum spend of KSh {coupon.minimum_spend:,.2f}.')

    customer_uses = DiscountApplication.objects.filter(coupon=coupon, customer=booking.customer).count()
    if customer_uses >= coupon.max_uses_per_customer:
        raise ValidationError('You\'ve already used this coupon the maximum number of times.')

    already_applied = DiscountApplication.objects.filter(booking=booking, source=DiscountSource.COUPON).exists()
    if already_applied:
        raise ValidationError('A coupon has already been applied to this booking.')

    if coupon.discount_type == DiscountType.PERCENTAGE:
        discount_amount = (invoice.total_amount * coupon.discount_value / Decimal('100')).quantize(Decimal('0.01'))
    else:
        discount_amount = min(coupon.discount_value, invoice.total_amount - invoice.amount_paid)

    if discount_amount <= 0:
        raise ValidationError('This coupon would not provide any discount on this invoice.')

    from apps.payments import services as payment_services
    with transaction.atomic():
        payment_services.apply_discount(invoice, discount_amount, reason=f'Coupon {coupon.code}')
        application = DiscountApplication.objects.create(
            booking=booking, customer=booking.customer, source=DiscountSource.COUPON,
            coupon=coupon, discount_amount=discount_amount,
        )
        Coupon.objects.filter(pk=coupon.pk).update(times_used=F('times_used') + 1)

    return application


# ============================================================
# Referrals
# ============================================================

def link_referral(customer, referral_code):
    """A customer retroactively enters someone else's referral code.
    Only allowed once, and only before their first booking, so this
    can't be gamed by an established customer."""
    profile = get_or_create_profile(customer)
    if profile.referred_by_id:
        raise ValidationError('A referral code has already been linked to your account.')
    if customer.bookings.exists():
        raise ValidationError('Referral codes can only be linked before your first booking.')

    try:
        referrer_profile = LoyaltyProfile.objects.select_related('customer').get(referral_code=referral_code.strip().upper())
    except LoyaltyProfile.DoesNotExist:
        raise ValidationError('That referral code was not found.')

    if referrer_profile.customer_id == customer.id:
        raise ValidationError('You cannot refer yourself.')

    profile.referred_by = referrer_profile.customer
    profile.save(update_fields=['referred_by', 'updated_at'])
    return profile


def _maybe_grant_referral_bonus(profile, booking):
    """Called when a referred customer's booking completes. Only fires
    once (referral_bonus_granted), and only for their first completed
    booking, per the customer's own account."""
    if not profile.referred_by_id or profile.referral_bonus_granted:
        return

    from apps.bookings.models import BookingStatus
    completed_count = booking.customer.bookings.filter(status=BookingStatus.COMPLETED).count()
    if completed_count != 1:
        return  # not their first completed booking

    referrer_profile = get_or_create_profile(profile.referred_by)
    award_points(
        referrer_profile, settings.LOYALTY_REFERRAL_BONUS_POINTS, PointsTransactionType.EARNED_REFERRAL,
        notes=f'Referred {profile.customer}',
    )
    if settings.LOYALTY_REFERRAL_BONUS_WALLET > 0:
        credit_wallet(
            referrer_profile, settings.LOYALTY_REFERRAL_BONUS_WALLET, WalletTransactionType.CREDIT_REFERRAL,
            notes=f'Referred {profile.customer}',
        )

    LoyaltyProfile.objects.filter(pk=profile.pk).update(referral_bonus_granted=True)

    from apps.notifications.utils import notify
    from apps.notifications.models import NotificationLevel
    notify(
        profile.referred_by.user, title='Referral bonus earned!',
        message=f'{profile.customer} completed their first booking -- you earned {settings.LOYALTY_REFERRAL_BONUS_POINTS} points.',
        level=NotificationLevel.SUCCESS, url=reverse('loyalty:my_dashboard'),
    )


# ============================================================
# Booking completion hook (called from apps.loyalty.signals)
# ============================================================

def handle_booking_completed(booking):
    if PointsTransaction.objects.filter(booking=booking, transaction_type=PointsTransactionType.EARNED_BOOKING).exists():
        return  # idempotent against re-saves at the same status

    profile = get_or_create_profile(booking.customer)
    points = points_for_booking(booking, profile.tier)
    award_points(profile, points, PointsTransactionType.EARNED_BOOKING, booking=booking, notes=booking.booking_code)
    _maybe_grant_referral_bonus(profile, booking)


# ============================================================
# Birthday rewards (see management command grant_birthday_rewards)
# ============================================================

def grant_birthday_rewards():
    """Meant to run once a day (any time of day) via cron/systemd
    timer. Idempotent per calendar year per customer."""
    from apps.customers.models import Customer

    today = timezone.localdate()
    granted = []
    candidates = Customer.objects.filter(
        date_of_birth__month=today.month, date_of_birth__day=today.day, is_active=True,
    ).select_related('user')

    for customer in candidates:
        profile = get_or_create_profile(customer)
        if profile.last_birthday_reward_year == today.year:
            continue

        award_points(
            profile, settings.LOYALTY_BIRTHDAY_BONUS_POINTS, PointsTransactionType.EARNED_BIRTHDAY,
            notes=f'Birthday {today.year}',
        )
        LoyaltyProfile.objects.filter(pk=profile.pk).update(last_birthday_reward_year=today.year)

        from apps.notifications.utils import notify
        from apps.notifications.models import NotificationLevel
        from apps.accounts.emails import send_branded_email

        notify(
            customer.user, title='Happy Birthday!',
            message=f'We\'ve added {settings.LOYALTY_BIRTHDAY_BONUS_POINTS} bonus points to your account.',
            level=NotificationLevel.SUCCESS, url=reverse('loyalty:my_dashboard'),
        )
        if customer.user.email:
            send_branded_email(
                subject='Happy Birthday from ShineHub',
                template_name='birthday_reward_email.html',
                context={'user': customer.user, 'points': settings.LOYALTY_BIRTHDAY_BONUS_POINTS},
                to_email=customer.user.email,
            )
        granted.append(customer)

    return granted
