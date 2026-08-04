from django import forms

FORM_INPUT_CLASSES = (
    'w-full rounded-lg border border-slate-700 bg-slate-900/60 px-3.5 py-2.5 text-sm text-white placeholder-gray-500 '
    'focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-colors'
)


class CashPaymentForm(forms.Form):
    amount = forms.DecimalField(
        min_value=1, max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'step': '0.01'}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': FORM_INPUT_CLASSES, 'placeholder': 'e.g. Paid at counter'}),
    )


class MpesaPaymentForm(forms.Form):
    phone_number = forms.CharField(
        widget=forms.TextInput(attrs={'class': FORM_INPUT_CLASSES, 'placeholder': '0712345678'}),
        help_text='The phone number that will receive the STK push prompt.',
    )
    amount = forms.DecimalField(
        min_value=1, max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'step': '0.01'}),
    )


class RefundForm(forms.Form):
    amount = forms.DecimalField(
        min_value=1, max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'step': '0.01'}),
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'class': FORM_INPUT_CLASSES, 'rows': 3, 'placeholder': 'Why is this being refunded?'}),
    )


class TransactionSearchForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': FORM_INPUT_CLASSES, 'placeholder': 'Search by reference, booking, or M-Pesa receipt...',
    }))
    method = forms.ChoiceField(
        required=False, choices=[('', 'All Methods'), ('cash', 'Cash'), ('mpesa', 'M-Pesa'), ('wallet', 'Loyalty Wallet')],
        widget=forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Statuses'), ('processing', 'Processing'), ('completed', 'Completed'),
                 ('failed', 'Failed'), ('cancelled', 'Cancelled')],
        widget=forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
    )
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': FORM_INPUT_CLASSES, 'type': 'date'}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': FORM_INPUT_CLASSES, 'type': 'date'}))


class CollectionsRangeForm(forms.Form):
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': FORM_INPUT_CLASSES, 'type': 'date'}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': FORM_INPUT_CLASSES, 'type': 'date'}))
