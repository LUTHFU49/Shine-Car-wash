import re

from django import forms
from django.core.exceptions import ValidationError

from apps.accounts.forms import StyledFormMixin
from apps.core.validators import validate_image_upload

from .models import WEEKDAY_CHOICES, Service, ServiceCategory

NAME_REGEX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\s\-&']*$")
MAX_REASONABLE_DURATION_MINUTES = 480  # 8 hours -- generous ceiling, catches fat-finger entry errors


class ServiceCategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ServiceCategory
        fields = ['name', 'description', 'icon', 'display_order']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False
        self.fields['display_order'].required = False

    def clean_name(self):
        value = self.cleaned_data['name'].strip()
        if not NAME_REGEX.match(value):
            raise ValidationError('Enter a valid category name.')
        qs = ServiceCategory.objects.filter(name__iexact=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('A category with this name already exists.')
        return value.title()


class ServiceForm(StyledFormMixin, forms.ModelForm):
    available_days = forms.MultipleChoiceField(
        choices=WEEKDAY_CHOICES, required=False, widget=forms.CheckboxSelectMultiple,
        help_text='Leave all unchecked to make this service available every day.',
    )

    class Meta:
        model = Service
        fields = ['category', 'name', 'description', 'price', 'duration_minutes', 'status', 'available_days', 'image']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'min': '1'}),
            'duration_minutes': forms.NumberInput(attrs={'min': '5'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = ServiceCategory.objects.filter(is_active=True)
        self.fields['description'].required = False
        self.fields['image'].required = False
        self.fields['status'].required = False

        if self.instance.pk and self.instance.available_days:
            self.initial['available_days'] = self.instance.available_days_list

    def clean_name(self):
        value = self.cleaned_data['name'].strip()
        if not NAME_REGEX.match(value):
            raise ValidationError('Enter a valid service name.')
        return value.title()

    def clean_price(self):
        value = self.cleaned_data['price']
        if value <= 0:
            raise ValidationError('Price must be a positive amount.')
        return value

    def clean_duration_minutes(self):
        value = self.cleaned_data['duration_minutes']
        if value <= 0:
            raise ValidationError('Duration must be a positive number of minutes.')
        if value > MAX_REASONABLE_DURATION_MINUTES:
            raise ValidationError(f'Duration seems too long (max {MAX_REASONABLE_DURATION_MINUTES} minutes). Double-check the value.')
        return value

    def clean_status(self):
        from .models import ServiceStatus
        return self.cleaned_data.get('status') or ServiceStatus.ACTIVE

    def clean_image(self):
        return validate_image_upload(self.cleaned_data.get('image'))

    def clean_available_days(self):
        selected = self.cleaned_data.get('available_days', [])
        # All 7 selected is functionally identical to "every day" (blank) --
        # normalize so available_days_display reads "Every day" either way.
        if len(selected) == len(WEEKDAY_CHOICES):
            return []
        return selected

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.available_days = ','.join(self.cleaned_data.get('available_days', []))
        if commit:
            instance.save()
        return instance


class ServiceSearchForm(forms.Form):
    q = forms.CharField(required=False)
    category = forms.ModelChoiceField(queryset=ServiceCategory.objects.all(), required=False)
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All statuses')] + list(Service._meta.get_field('status').choices),
    )
    sort = forms.ChoiceField(
        required=False,
        choices=[('name', 'Name (A-Z)'), ('-price', 'Price (high to low)'), ('price', 'Price (low to high)'), ('-created_at', 'Newest first')],
    )
