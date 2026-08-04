from django.urls import path

from . import views

app_name = 'loyalty'

urlpatterns = [
    # Customer self-service
    path('my/', views.my_dashboard_view, name='my_dashboard'),
    path('my/referral/', views.enter_referral_code_view, name='enter_referral_code'),
    path('my/booking/<uuid:booking_public_id>/apply-coupon/', views.apply_coupon_view, name='apply_coupon'),
    path('my/booking/<uuid:booking_public_id>/pay-wallet/', views.pay_with_wallet_view, name='pay_with_wallet'),

    # Staff management
    path('tiers/', views.tier_list_view, name='tier_list'),
    path('tiers/create/', views.tier_create_view, name='tier_create'),
    path('tiers/<uuid:public_id>/edit/', views.tier_edit_view, name='tier_edit'),

    path('coupons/', views.coupon_list_view, name='coupon_list'),
    path('coupons/create/', views.coupon_create_view, name='coupon_create'),
    path('coupons/<uuid:public_id>/edit/', views.coupon_edit_view, name='coupon_edit'),
    path('coupons/<uuid:public_id>/status/<str:new_status>/', views.coupon_set_status_view, name='coupon_set_status'),

    path('promotions/', views.promotion_history_view, name='promotion_history'),
    path('promotions/export/', views.promotion_history_export_view, name='promotion_history_export'),

    path('members/', views.member_list_view, name='member_list'),
]
