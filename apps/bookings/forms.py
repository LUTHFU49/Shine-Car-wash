from django import forms
from django.utils import timezone

from apps.accounts.forms import StyledFormMixin
from apps.services.models import Service

from .models import Booking, BookingStatus


class BaseBookingForm(StyledFormMixin, forms.ModelForm):
    """
    Shared base for the customer and staff booking forms. The heavy
    validation (past dates, business hours, service day-availability,
    vehicle double-booking) lives on Booking.clean() and runs
    automatically as part of ModelForm.is_valid() -- it is not
    duplicated here.
    """

    class Meta:
        model = Booking
        fields = ['vehicle', 'service', 'scheduled_date', 'scheduled_time', 'notes']
        widgets = {
            'scheduled_date': forms.DateInput(attrs={'type': 'date'}),
            'scheduled_time': forms.TimeInput(attrs={'type': 'time'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['notes'].required = False
        self.fields['scheduled_date'].widget.attrs['min'] = timezone.localdate().isoformat()
        self.fields['service'].queryset = Service.objects.filter(status='active').select_related('category')


class CustomerBookingForm(BaseBookingForm):
    """Self-service booking -- vehicle choices are restricted to the logged-in customer's own active vehicles."""

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        if customer is not None:
            self.fields['vehicle'].queryset = customer.vehicles.filter(status='active')


class StaffBookingForm(BaseBookingForm):
    """Staff walk-in / phone booking -- vehicle choices are restricted to whichever customer staff picked."""

    class Meta(BaseBookingForm.Meta):
        fields = BaseBookingForm.Meta.fields + ['staff_notes']
        widgets = {**BaseBookingForm.Meta.widgets, 'staff_notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['staff_notes'].required = False
        if customer is not None:
            self.fields['vehicle'].queryset = customer.vehicles.filter(status='active')


class RescheduleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['scheduled_date', 'scheduled_time']
        widgets = {
            'scheduled_date': forms.DateInput(attrs={'type': 'date'}),
            'scheduled_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['scheduled_date'].widget.attrs['min'] = timezone.localdate().isoformat()


class CancelBookingForm(StyledFormMixin, forms.Form):
    reason = forms.CharField(
        required=False, max_length=255, widget=forms.Textarea(attrs={'rows': 2}),
        label='Reason (optional)',
    )


class BookingSearchForm(forms.Form):
    q = forms.CharField(required=False)
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All statuses')] + list(BookingStatus.choices),
    )
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
