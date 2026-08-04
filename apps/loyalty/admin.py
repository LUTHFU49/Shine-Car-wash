from django.contrib import admin

from .models import (
    Coupon, DiscountApplication, LoyaltyProfile, LoyaltyTier,
    PointsTransaction, WalletTransaction,
)


@admin.register(LoyaltyTier)
class LoyaltyTierAdmin(admin.ModelAdmin):
    list_display = ('name', 'minimum_points', 'discount_percentage', 'points_multiplier', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)
    readonly_fields = ('public_id', 'created_at', 'updated_at')


@admin.register(LoyaltyProfile)
class LoyaltyProfileAdmin(admin.ModelAdmin):
    list_display = ('customer', 'tier', 'points_balance', 'lifetime_points', 'wallet_balance', 'referral_code')
    list_filter = ('tier',)
    search_fields = ('customer__first_name', 'customer__last_name', 'referral_code')
    autocomplete_fields = ('customer', 'tier', 'referred_by')
    readonly_fields = (
        'public_id', 'points_balance', 'lifetime_points', 'wallet_balance', 'referral_code',
        'referral_bonus_granted', 'last_birthday_reward_year', 'created_at', 'updated_at',
    )


@admin.register(PointsTransaction)
class PointsTransactionAdmin(admin.ModelAdmin):
    list_display = ('profile', 'transaction_type', 'points', 'booking', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    autocomplete_fields = ('profile', 'booking')
    readonly_fields = [f.name for f in PointsTransaction._meta.fields]  # append-only ledger

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('profile', 'transaction_type', 'amount', 'payment', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    autocomplete_fields = ('profile', 'payment')
    readonly_fields = [f.name for f in WalletTransaction._meta.fields]  # append-only ledger

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'discount_value', 'times_used', 'max_uses', 'is_active', 'valid_until')
    list_filter = ('is_active', 'discount_type')
    search_fields = ('code', 'description')
    readonly_fields = ('public_id', 'times_used', 'created_at', 'updated_at')


@admin.register(DiscountApplication)
class DiscountApplicationAdmin(admin.ModelAdmin):
    list_display = ('booking', 'customer', 'source', 'coupon', 'discount_amount', 'applied_at')
    list_filter = ('source', 'applied_at')
    search_fields = ('booking__vehicle__license_plate', 'customer__first_name', 'customer__last_name', 'coupon__code')
    autocomplete_fields = ('booking', 'customer', 'coupon')
    readonly_fields = [f.name for f in DiscountApplication._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
