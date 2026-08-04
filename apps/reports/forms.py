from django import forms

from .models import Expense, ExpenseCategory

FORM_INPUT_CLASSES = (
    'w-full rounded-lg border border-slate-700 bg-slate-900/60 px-3.5 py-2.5 text-sm text-white placeholder-gray-500 '
    'focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-colors'
)


class DateRangeForm(forms.Form):
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': FORM_INPUT_CLASSES, 'type': 'date'}))
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': FORM_INPUT_CLASSES, 'type': 'date'}))

    def clean(self):
        cleaned_data = super().clean()
        start, end = cleaned_data.get('start'), cleaned_data.get('end')
        if start and end and start > end:
            raise forms.ValidationError('Start date must be on or before the end date.')
        return cleaned_data


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES}),
            'description': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES}),
            'is_active': forms.CheckboxInput(attrs={'class': 'rounded border-slate-600 bg-slate-900 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-800'}),
        }


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['category', 'description', 'amount', 'expense_date', 'notes']
        widgets = {
            'category': forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
            'description': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES}),
            'amount': forms.NumberInput(attrs={'class': FORM_INPUT_CLASSES, 'step': '0.01', 'min': 1}),
            'expense_date': forms.DateInput(attrs={'class': FORM_INPUT_CLASSES, 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': FORM_INPUT_CLASSES, 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = ExpenseCategory.objects.filter(is_active=True)
