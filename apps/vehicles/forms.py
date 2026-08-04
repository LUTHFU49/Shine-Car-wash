import re

from django import forms
from django.core.exceptions import ValidationError

from apps.accounts.forms import StyledFormMixin
from apps.core.validators import normalize_kenyan_license_plate, validate_image_upload

from .models import Vehicle

MAKE_MODEL_REGEX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\s\-]*$")


class VehicleFormBase(StyledFormMixin, forms.ModelForm):
    """Shared validation between the staff and customer-facing forms."""

    class Meta:
        model = Vehicle
        fields = ['license_plate', 'make', 'model', 'year', 'color', 'vehicle_type', 'photo']
        widgets = {
            'year': forms.NumberInput(attrs={'min': 1980}),
        }

    def clean_license_plate(self):
        raw = self.cleaned_data['license_plate']
        normalized = normalize_kenyan_license_plate(raw)
        qs = Vehicle.objects.filter(license_plate=normalized)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('A vehicle with this license plate is already registered.')
        return normalized

    def clean_make(self):
        value = self.cleaned_data['make'].strip()
        if not MAKE_MODEL_REGEX.match(value):
            raise ValidationError('Enter a valid make (letters, numbers, spaces, and hyphens only).')
        return value.title()

    def clean_model(self):
        value = self.cleaned_data['model'].strip()
        if not MAKE_MODEL_REGEX.match(value):
            raise ValidationError('Enter a valid model (letters, numbers, spaces, and hyphens only).')
        return value.title()

    def clean_color(self):
        value = self.cleaned_data['color'].strip()
        if not re.match(r'^[A-Za-z\s\-]+$', value):
            raise ValidationError('Enter a valid color (letters only).')
        return value.title()

    def clean_photo(self):
        return validate_image_upload(self.cleaned_data.get('photo'))


class VehicleForm(VehicleFormBase):
    """Full staff-facing form -- includes status and internal notes."""

    class Meta(VehicleFormBase.Meta):
        fields = VehicleFormBase.Meta.fields + ['status', 'notes']
        widgets = {**VehicleFormBase.Meta.widgets, 'notes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False
        self.fields['photo'].required = False
        self.fields['status'].required = False

    def clean_status(self):
        from .models import VehicleStatus
        return self.cleaned_data.get('status') or VehicleStatus.ACTIVE


class CustomerVehicleForm(VehicleFormBase):
    """
    Restricted form used on the customer-facing "My Vehicles" pages.
    No `status` or `notes` fields -- those are staff-only concerns.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['photo'].required = False


class VehicleSearchForm(forms.Form):
    """Drives the staff vehicle list view's querystring -- not a ModelForm."""
    q = forms.CharField(required=False)
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All statuses')] + list(Vehicle._meta.get_field('status').choices),
    )
    vehicle_type = forms.ChoiceField(
        required=False,
        choices=[('', 'All types')] + list(Vehicle._meta.get_field('vehicle_type').choices),
    )
    sort = forms.ChoiceField(
        required=False,
        choices=[('-created_at', 'Newest first'), ('created_at', 'Oldest first'), ('license_plate', 'License Plate (A-Z)')],
    )
