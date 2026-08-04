from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit_logs.models import AuditLog
from apps.core.decorators import customer_required, management_required

from . import services
from .forms import ApplyCouponForm, CouponForm, LoyaltyTierForm, ReferralCodeForm, WalletPaymentForm
from .models import Coupon, DiscountApplication, LoyaltyProfile, LoyaltyTier

PAGE_SIZE = 20


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log(request, action, model_name, obj, description):
    AuditLog.objects.create(
        user=request.user, action=action, model_name=model_name,
        object_id=str(obj.pk), description=description,
        ip_address=_client_ip(request),
    )


# ============================================================
# Customer self-service
# ============================================================

@customer_required
def my_dashboard_view(request):
    customer = request.user.customer_profile
    profile = services.get_or_create_profile(customer)

    next_tier = (
        LoyaltyTier.objects.filter(is_active=True, minimum_points__gt=profile.lifetime_points)
        .order_by('minimum_points').first()
    )
    points_to_next_tier = (next_tier.minimum_points - profile.lifetime_points) if next_tier else None
    points_transactions = profile.points_transactions.all()[:10]
    wallet_transactions = profile.wallet_transactions.all()[:10]
    referral_count = LoyaltyProfile.objects.filter(referred_by=customer).count()

    return render(request, 'loyalty/my_dashboard.html', {
        'profile': profile, 'next_tier': next_tier, 'points_to_next_tier': points_to_next_tier,
        'points_transactions': points_transactions, 'wallet_transactions': wallet_transactions,
        'referral_count': referral_count, 'referral_form': ReferralCodeForm(),
    })


@customer_required
@require_POST
def enter_referral_code_view(request):
    customer = request.user.customer_profile
    form = ReferralCodeForm(request.POST)
    if form.is_valid():
        try:
            services.link_referral(customer, form.cleaned_data['referral_code'])
            messages.success(request, 'Referral code linked to your account.')
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
    else:
        messages.error(request, 'Please enter a valid referral code.')
    return redirect('loyalty:my_dashboard')


@customer_required
@require_POST
def apply_coupon_view(request, booking_public_id):
    from apps.bookings.models import Booking

    booking = get_object_or_404(Booking, public_id=booking_public_id, customer__user=request.user)
    form = ApplyCouponForm(request.POST)
    if form.is_valid():
        try:
            services.validate_and_apply_coupon(booking, form.cleaned_data['code'], request.user)
            messages.success(request, 'Coupon applied.')
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
    else:
        messages.error(request, 'Please enter a coupon code.')
    return redirect('bookings:my_detail', public_id=booking.public_id)


@customer_required
@require_POST
def pay_with_wallet_view(request, booking_public_id):
    from apps.bookings.models import Booking

    booking = get_object_or_404(Booking, public_id=booking_public_id, customer__user=request.user)
    invoice = getattr(booking, 'invoice', None)
    if invoice is None:
        messages.error(request, 'This booking has no invoice yet.')
        return redirect('bookings:my_detail', public_id=booking.public_id)

    form = WalletPaymentForm(request.POST)
    if form.is_valid():
        profile = services.get_or_create_profile(booking.customer)
        try:
            services.pay_with_wallet(invoice, profile, form.cleaned_data['amount'], request.user)
            messages.success(request, 'Payment made from your loyalty wallet.')
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
    else:
        messages.error(request, 'Please enter a valid amount.')
    return redirect('bookings:my_detail', public_id=booking.public_id)


# ============================================================
# Staff: Tiers
# ============================================================

@management_required
def tier_list_view(request):
    tiers = LoyaltyTier.objects.annotate(member_count=Count('members')).order_by('minimum_points')
    return render(request, 'loyalty/tier_list.html', {'tiers': tiers})


@management_required
def tier_create_view(request):
    if request.method == 'POST':
        form = LoyaltyTierForm(request.POST)
        if form.is_valid():
            tier = form.save(commit=False)
            tier.created_by = request.user
            tier.save()
            _log(request, AuditLog.Action.CREATE, 'LoyaltyTier', tier, f'Created tier "{tier.name}"')
            messages.success(request, f'{tier.name} tier created.')
            return redirect('loyalty:tier_list')
    else:
        form = LoyaltyTierForm()
    return render(request, 'loyalty/tier_form.html', {'form': form, 'is_create': True})


@management_required
def tier_edit_view(request, public_id):
    tier = get_object_or_404(LoyaltyTier, public_id=public_id)
    if request.method == 'POST':
        form = LoyaltyTierForm(request.POST, instance=tier)
        if form.is_valid():
            form.save()
            _log(request, AuditLog.Action.UPDATE, 'LoyaltyTier', tier, f'Updated tier "{tier.name}"')
            messages.success(request, 'Tier updated.')
            return redirect('loyalty:tier_list')
    else:
        form = LoyaltyTierForm(instance=tier)
    return render(request, 'loyalty/tier_form.html', {'form': form, 'is_create': False, 'tier': tier})


# ============================================================
# Staff: Coupons
# ============================================================

@management_required
def coupon_list_view(request):
    coupons = Coupon.objects.order_by('-created_at')
    return render(request, 'loyalty/coupon_list.html', {'coupons': coupons})


@management_required
def coupon_create_view(request):
    if request.method == 'POST':
        form = CouponForm(request.POST)
        if form.is_valid():
            coupon = form.save(commit=False)
            coupon.created_by = request.user
            coupon.save()
            _log(request, AuditLog.Action.CREATE, 'Coupon', coupon, f'Created coupon "{coupon.code}"')
            messages.success(request, f'Coupon {coupon.code} created.')
            return redirect('loyalty:coupon_list')
    else:
        form = CouponForm()
    return render(request, 'loyalty/coupon_form.html', {'form': form, 'is_create': True})


@management_required
def coupon_edit_view(request, public_id):
    coupon = get_object_or_404(Coupon, public_id=public_id)
    if request.method == 'POST':
        form = CouponForm(request.POST, instance=coupon)
        if form.is_valid():
            form.save()
            _log(request, AuditLog.Action.UPDATE, 'Coupon', coupon, f'Updated coupon "{coupon.code}"')
            messages.success(request, 'Coupon updated.')
            return redirect('loyalty:coupon_list')
    else:
        form = CouponForm(instance=coupon)
    return render(request, 'loyalty/coupon_form.html', {'form': form, 'is_create': False, 'coupon': coupon})


@management_required
@require_POST
def coupon_set_status_view(request, public_id, new_status):
    coupon = get_object_or_404(Coupon, public_id=public_id)
    coupon.is_active = new_status == 'active'
    coupon.save(update_fields=['is_active'])
    _log(request, AuditLog.Action.UPDATE, 'Coupon', coupon, f'Status set to {new_status} for "{coupon.code}"')
    messages.success(request, f'Coupon marked as {"active" if coupon.is_active else "inactive"}.')
    return redirect('loyalty:coupon_list')


# ============================================================
# Staff: Promotion history + member list
# ============================================================

@management_required
def promotion_history_view(request):
    applications = DiscountApplication.objects.select_related('booking', 'customer', 'coupon').order_by('-applied_at')

    source = request.GET.get('source')
    if source in ('tier', 'coupon'):
        applications = applications.filter(source=source)

    paginator = Paginator(applications, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    total_discounted = applications.aggregate(total=Sum('discount_amount'))['total'] or 0

    return render(request, 'loyalty/promotion_history.html', {'page_obj': page_obj, 'total_discounted': total_discounted})


@management_required
def promotion_history_export_view(request):
    from apps.reports import exports

    applications = DiscountApplication.objects.select_related('booking', 'customer', 'coupon').order_by('-applied_at')
    headers = ['Date', 'Booking', 'Customer', 'Source', 'Coupon', 'Discount (KSh)']
    rows = [[
        a.applied_at.strftime('%Y-%m-%d %H:%M'), a.booking.booking_code,
        f'{a.customer.first_name} {a.customer.last_name}', a.get_source_display(),
        a.coupon.code if a.coupon_id else '', a.discount_amount,
    ] for a in applications]

    fmt = request.GET.get('format', 'csv').lower()
    if fmt == 'excel':
        return exports.excel_response('shinehub-promotion-history', 'Promotion History', headers, rows)
    if fmt == 'pdf':
        return exports.pdf_response('shinehub-promotion-history', 'Promotion History', '', headers, rows)
    return exports.csv_response('shinehub-promotion-history', headers, rows)


@management_required
def member_list_view(request):
    profiles = LoyaltyProfile.objects.select_related('customer', 'tier').order_by('-lifetime_points')

    q = request.GET.get('q', '').strip()
    if q:
        profiles = profiles.filter(
            Q(customer__first_name__icontains=q) | Q(customer__last_name__icontains=q) | Q(referral_code__icontains=q),
        )

    paginator = Paginator(profiles, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'loyalty/member_list.html', {'page_obj': page_obj, 'q': q})
