from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from apps.core.validators import validate_image_upload

from .models import (
    InventoryCategory, InventoryItem, Purchase, PurchaseItem,
    ServiceInventoryRequirement, Supplier,
)

FORM_INPUT_CLASSES = (
    'w-full rounded-lg border border-slate-700 bg-slate-900/60 px-3.5 py-2.5 text-sm text-white placeholder-gray-500 '
    'focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-colors'
)


class InventoryCategoryForm(forms.ModelForm):
    class Meta:
        model = InventoryCategory
        fields = ['name', 'description', 'icon', 'display_order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES}),
            'description': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES}),
            'icon': forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
            'display_order': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-600 bg-slate-900 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-800'}),
        }


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'contact_person', 'phone_number', 'email', 'address', 'notes', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES}),
            'contact_person': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES}),
            'phone_number': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES, 'placeholder': '0712345678'}),
            'email': forms.EmailInput(attrs={'class': FORM_INPUT_CLASSES}),
            'address': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES}),
            'notes': forms.Textarea(attrs={'class': FORM_INPUT_CLASSES, 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-600 bg-slate-900 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-800'}),
        }


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = [
            'category', 'name', 'description', 'unit', 'reorder_level',
            'track_expiry', 'image', 'is_active',
        ]
        widgets = {
            'category': forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
            'name': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES}),
            'description': forms.Textarea(attrs={'class': FORM_INPUT_CLASSES, 'rows': 3}),
            'unit': forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
            'reorder_level': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES}),
            'track_expiry': forms.CheckboxInput(attrs={'class': 'rounded border-slate-600 bg-slate-900 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-800'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-600 bg-slate-900 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-800'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = InventoryCategory.objects.filter(is_active=True)

    def clean_image(self):
        image = self.cleaned_data.get('image')
        return validate_image_upload(image) if image else image


class ItemSearchForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': FORM_INPUT_CLASSES, 'placeholder': 'Search by name or SKU...',
    }))
    category = forms.ModelChoiceField(
        required=False, queryset=InventoryCategory.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
    )
    stock_state = forms.ChoiceField(
        required=False,
        choices=[('', 'All Stock Levels'), ('low', 'Low Stock'), ('out', 'Out of Stock')],
        widget=forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Statuses'), ('active', 'Active'), ('inactive', 'Inactive')],
        widget=forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
    )


class CSVImportForm(forms.Form):
    csv_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={'class': FORM_INPUT_CLASSES, 'accept': '.csv'}),
        help_text='Columns: name, category, unit, reorder_level, track_expiry (yes/no)',
    )

    def clean_csv_file(self):
        file = self.cleaned_data['csv_file']
        if not file.name.lower().endswith('.csv'):
            raise ValidationError('Please upload a .csv file.')
        if file.size > 2 * 1024 * 1024:
            raise ValidationError('CSV file must be smaller than 2MB.')
        return file


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ['supplier', 'order_date', 'expected_date', 'notes']
        widgets = {
            'supplier': forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
            'order_date': forms.DateInput(attrs={'class': FORM_INPUT_CLASSES, 'type': 'date'}),
            'expected_date': forms.DateInput(attrs={'class': FORM_INPUT_CLASSES, 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': FORM_INPUT_CLASSES, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)


class PurchaseItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseItem
        fields = ['item', 'quantity_ordered', 'unit_cost', 'expiry_date']
        widgets = {
            'item': forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
            'quantity_ordered': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'min': 1}),
            'unit_cost': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'step': '0.01', 'min': 0}),
            'expiry_date': forms.DateInput(attrs={'class': FORM_INPUT_CLASSES, 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = InventoryItem.objects.filter(is_active=True)
        self.fields['expiry_date'].required = False


PurchaseItemFormSet = inlineformset_factory(
    Purchase, PurchaseItem, form=PurchaseItemForm,
    extra=1, can_delete=True, min_num=1, validate_min=True,
)


class StockAdjustmentForm(forms.Form):
    direction = forms.ChoiceField(choices=[('in', 'Stock In'), ('out', 'Stock Out')],
                                   widget=forms.Select(attrs={'class': FORM_INPUT_CLASSES}))
    quantity = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES}))
    reason = forms.CharField(widget=forms.TextInput(attrs={
        'class': FORM_INPUT_CLASSES, 'placeholder': 'e.g. Physical stock count correction',
    }))


class DamageReportForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES}))
    reason = forms.CharField(widget=forms.Textarea(attrs={
        'class': FORM_INPUT_CLASSES, 'rows': 2, 'placeholder': 'What happened to this stock?',
    }))


class ServiceInventoryRequirementForm(forms.ModelForm):
    class Meta:
        model = ServiceInventoryRequirement
        fields = ['service', 'item', 'quantity_required']
        widgets = {
            'service': forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
            'item': forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
            'quantity_required': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'min': 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = InventoryItem.objects.filter(is_active=True)
