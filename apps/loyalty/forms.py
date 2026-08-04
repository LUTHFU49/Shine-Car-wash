from django import forms

from .models import Coupon, LoyaltyTier

FORM_INPUT_CLASSES = (
    'w-full rounded-lg border border-slate-700 bg-slate-900/60 px-3.5 py-2.5 text-sm text-white placeholder-gray-500 '
    'focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-colors'
)


class LoyaltyTierForm(forms.ModelForm):
    class Meta:
        model = LoyaltyTier
        fields = ['name', 'minimum_points', 'discount_percentage', 'points_multiplier', 'icon', 'display_order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES}),
            'minimum_points': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'min': 0}),
            'discount_percentage': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'step': '0.01', 'min': 0, 'max': 100}),
            'points_multiplier': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'step': '0.01', 'min': 0}),
            'icon': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES, 'placeholder': 'fa-medal'}),
            'display_order': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-600 bg-slate-900 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-800'}),
        }


class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = [
            'code', 'description', 'discount_type', 'discount_value', 'minimum_spend',
            'max_uses', 'max_uses_per_customer', 'valid_from', 'valid_until', 'is_active',
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES, 'placeholder': 'SAVE20'}),
            'description': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES}),
            'discount_type': forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
            'discount_value': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'step': '0.01', 'min': 0}),
            'minimum_spend': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'step': '0.01', 'min': 0}),
            'max_uses': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'min': 1}),
            'max_uses_per_customer': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'min': 1}),
            'valid_from': forms.DateInput(attrs={'class': FORM_INPUT_CLASSES, 'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'class': FORM_INPUT_CLASSES, 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-600 bg-slate-900 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-800'}),
        }

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()


class ReferralCodeForm(forms.Form):
    referral_code = forms.CharField(
        max_length=20, widget=forms.TextInput(attrs={'class': FORM_INPUT_CLASSES, 'placeholder': 'REF-ABC123'}),
    )


class ApplyCouponForm(forms.Form):
    code = forms.CharField(
        max_length=30, widget=forms.TextInput(attrs={'class': FORM_INPUT_CLASSES, 'placeholder': 'Promo code'}),
    )


class WalletPaymentForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=1,
        widget=forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'step': '0.01'}),
    )
