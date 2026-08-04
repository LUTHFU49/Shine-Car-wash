import re

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.accounts.forms import StyledFormMixin, validate_person_name
from apps.accounts.models import phone_validator

from .models import AttendanceRecord, Employee, EmployeePosition, EmploymentStatus, PerformanceReview, WEEKDAY_CHOICES

User = get_user_model()


class EmployeeOnboardingForm(StyledFormMixin, forms.Form):
    """
    Creates the User login account and the Employee HR profile together
    in one step. The new employee gets a "set your password" email
    (reusing the same token flow as forgot-password) rather than being
    handed a plaintext password.
    """
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone_number = forms.CharField(max_length=17, validators=[phone_validator])

    position = forms.ChoiceField(choices=EmployeePosition.choices)
    hire_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    scheduled_days = forms.MultipleChoiceField(choices=WEEKDAY_CHOICES, required=False, widget=forms.CheckboxSelectMultiple)
    shift_start_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    shift_end_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))

    def clean_first_name(self):
        value = self.cleaned_data['first_name'].strip()
        validate_person_name(value, 'First name')
        return value.title()

    def clean_last_name(self):
        value = self.cleaned_data['last_name'].strip()
        validate_person_name(value, 'Last name')
        return value.title()

    def clean_username(self):
        value = self.cleaned_data['username'].strip()
        if not re.match(r'^[A-Za-z0-9_.]{3,150}$', value):
            raise ValidationError('Username must be 3+ characters: letters, numbers, dots, and underscores only.')
        if User.objects.filter(username__iexact=value).exists():
            raise ValidationError('This username is already taken.')
        return value

    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        validate_email(value)
        if User.objects.filter(email__iexact=value).exists():
            raise ValidationError('An account with this email already exists.')
        return value

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('shift_start_time')
        end = cleaned.get('shift_end_time')
        if start and end and start >= end:
            raise ValidationError('Shift end time must be after the shift start time.')
        return cleaned


class EmployeeEditForm(StyledFormMixin, forms.ModelForm):
    """Edits the HR profile only -- name/email/phone changes go through the linked User's own profile."""

    scheduled_days = forms.MultipleChoiceField(choices=WEEKDAY_CHOICES, required=False, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Employee
        fields = ['position', 'employment_status', 'termination_date', 'scheduled_days', 'shift_start_time', 'shift_end_time', 'notes']
        widgets = {
            'termination_date': forms.DateInput(attrs={'type': 'date'}),
            'shift_start_time': forms.TimeInput(attrs={'type': 'time'}),
            'shift_end_time': forms.TimeInput(attrs={'type': 'time'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['termination_date'].required = False
        self.fields['notes'].required = False
        if self.instance.pk and self.instance.scheduled_days:
            self.initial['scheduled_days'] = self.instance.scheduled_days_list

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get('employment_status')
        termination_date = cleaned.get('termination_date')
        if status == EmploymentStatus.TERMINATED and not termination_date:
            raise ValidationError('Set a termination date when marking an employee as Terminated.')
        start = cleaned.get('shift_start_time')
        end = cleaned.get('shift_end_time')
        if start and end and start >= end:
            raise ValidationError('Shift end time must be after the shift start time.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.scheduled_days = ','.join(self.cleaned_data.get('scheduled_days', []))
        if commit:
            instance.save()
        return instance


class AttendanceForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ['date', 'status', 'clock_in_time', 'clock_out_time', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'clock_in_time': forms.TimeInput(attrs={'type': 'time'}),
            'clock_out_time': forms.TimeInput(attrs={'type': 'time'}),
            'notes': forms.TextInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['clock_in_time'].required = False
        self.fields['clock_out_time'].required = False
        self.fields['notes'].required = False

    def clean(self):
        cleaned = super().clean()
        clock_in = cleaned.get('clock_in_time')
        clock_out = cleaned.get('clock_out_time')
        if clock_in and clock_out and clock_in >= clock_out:
            raise ValidationError('Clock-out time must be after clock-in time.')
        return cleaned


class PerformanceReviewForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PerformanceReview
        fields = ['review_date', 'rating', 'comments']
        widgets = {
            'review_date': forms.DateInput(attrs={'type': 'date'}),
            'rating': forms.Select(choices=[(i, f'{i} / 5') for i in range(1, 6)]),
            'comments': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['comments'].required = False


class EmployeeSearchForm(forms.Form):
    q = forms.CharField(required=False)
    position = forms.ChoiceField(required=False, choices=[('', 'All positions')] + list(EmployeePosition.choices))
    status = forms.ChoiceField(required=False, choices=[('', 'All statuses')] + list(EmploymentStatus.choices))
