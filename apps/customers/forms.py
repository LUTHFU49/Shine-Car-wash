import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.accounts.forms import StyledFormMixin, validate_person_name

from .models import Customer

NAME_REGEX = re.compile(r"^[A-Za-z][A-Za-z\s\-']*$")


class CustomerForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'first_name', 'last_name', 'email', 'phone_number',
            'date_of_birth', 'address', 'notes',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'maxlength': 500}),
            'address': forms.TextInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = False
        self.fields['date_of_birth'].required = False
        self.fields['address'].required = False
        self.fields['notes'].required = False

    def clean_first_name(self):
        value = self.cleaned_data['first_name'].strip()
        validate_person_name(value, 'First name')
        return value.title()

    def clean_last_name(self):
        value = self.cleaned_data['last_name'].strip()
        validate_person_name(value, 'Last name')
        return value.title()

    def clean_email(self):
        value = self.cleaned_data.get('email', '').strip().lower()
        if not value:
            return value
        validate_email(value)
        qs = Customer.objects.filter(email__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('Another customer already uses this email address.')
        return value

    def clean_phone_number(self):
        value = self.cleaned_data['phone_number'].strip()
        digits_only = re.sub(r'\D', '', value)
        if not (9 <= len(digits_only) <= 15):
            raise ValidationError('Enter a valid phone number (9 to 15 digits).')
        qs = Customer.objects.filter(phone_number=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('Another customer already uses this phone number.')
        return value

    def clean_date_of_birth(self):
        from django.utils import timezone
        value = self.cleaned_data.get('date_of_birth')
        if value and value > timezone.now().date():
            raise ValidationError('Date of birth cannot be in the future.')
        return value


class CustomerSearchForm(forms.Form):
    """Not a ModelForm -- this only drives the list view's querystring."""
    q = forms.CharField(required=False)
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All statuses'), ('active', 'Active'), ('inactive', 'Deactivated')],
    )
    source = forms.ChoiceField(
        required=False,
        choices=[('', 'All sources'), ('linked', 'Registered online'), ('walkin', 'Walk-in')],
    )
    sort = forms.ChoiceField(
        required=False,
        choices=[('-created_at', 'Newest first'), ('created_at', 'Oldest first'), ('name', 'Name (A-Z)')],
    )
