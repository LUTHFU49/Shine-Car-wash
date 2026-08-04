import re

from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import User

NAME_REGEX = re.compile(r"^[A-Za-z][A-Za-z\s\-']*$")

TEXT_INPUT_CLASSES = (
    'w-full rounded-lg border border-slate-700 bg-slate-900/60 px-4 py-2.5 '
    'text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:ring-1 '
    'focus:ring-blue-500 outline-none transition-colors'
)
CHECKBOX_CLASSES = 'w-4 h-4 rounded border-slate-600 bg-slate-900 text-blue-500 focus:ring-blue-500 focus:ring-offset-slate-800'


class StyledFormMixin:
    """Applies consistent Tailwind classes to every widget so templates
    can render `{{ form.field }}` directly without repeating classes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', CHECKBOX_CLASSES)
            else:
                widget.attrs.setdefault('class', TEXT_INPUT_CLASSES)
                widget.attrs.setdefault('placeholder', field.label or name.replace('_', ' ').title())


def validate_person_name(value, field_label='This field'):
    if not NAME_REGEX.match(value.strip()):
        raise ValidationError(f'{field_label} may only contain letters, spaces, hyphens, and apostrophes.')


class RegistrationForm(StyledFormMixin, forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={
        'minlength': 2, 'pattern': "[A-Za-z\\s\\-']+", 'autocomplete': 'given-name',
    }))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={
        'minlength': 2, 'pattern': "[A-Za-z\\s\\-']+", 'autocomplete': 'family-name',
    }))
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={
        'minlength': 3, 'pattern': '[A-Za-z0-9_.]+', 'autocomplete': 'username',
    }))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    phone_number = forms.CharField(max_length=17, widget=forms.TextInput(attrs={
        'autocomplete': 'tel', 'placeholder': 'e.g. 0712345678',
    }))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={
        'minlength': 8, 'autocomplete': 'new-password', 'data-password-strength': 'true',
    }), label='Password')
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={
        'minlength': 8, 'autocomplete': 'new-password',
    }), label='Confirm password')
    agree_to_terms = forms.BooleanField(required=True, label='I agree to the Terms of Service')

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
        if len(value) < 3:
            raise ValidationError('Username must be at least 3 characters long.')
        if not re.match(r'^[A-Za-z0-9_.]+$', value):
            raise ValidationError('Username may only contain letters, numbers, underscores, and periods.')
        if User.objects.filter(username__iexact=value).exists():
            raise ValidationError('That username is already taken.')
        return value

    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        validate_email(value)
        if User.objects.filter(email__iexact=value).exists():
            raise ValidationError('An account with this email already exists.')
        return value

    def clean_phone_number(self):
        value = self.cleaned_data['phone_number'].strip()
        digits_only = re.sub(r'\D', '', value)
        if not (9 <= len(digits_only) <= 15):
            raise ValidationError('Enter a valid phone number (9 to 15 digits).')
        return value

    def clean_agree_to_terms(self):
        value = self.cleaned_data['agree_to_terms']
        if not value:
            raise ValidationError('You must agree to the Terms of Service to create an account.')
        return value

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2:
            if password1 != password2:
                self.add_error('password2', 'Passwords do not match.')
            else:
                # Run Django's full password validator chain (length,
                # similarity to user attrs, common-password list,
                # numeric-only check, and our ComplexPasswordValidator).
                dummy_user = User(
                    username=cleaned_data.get('username', ''),
                    email=cleaned_data.get('email', ''),
                    first_name=cleaned_data.get('first_name', ''),
                    last_name=cleaned_data.get('last_name', ''),
                )
                try:
                    password_validation.validate_password(password1, user=dummy_user)
                except ValidationError as exc:
                    self.add_error('password1', exc)

        return cleaned_data


class LoginForm(StyledFormMixin, forms.Form):
    username = forms.CharField(label='Username or email')
    password = forms.CharField(widget=forms.PasswordInput)
    remember_me = forms.BooleanField(required=False)


class ForgotPasswordForm(StyledFormMixin, forms.Form):
    email = forms.EmailField()

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class SetNewPasswordForm(StyledFormMixin, forms.Form):
    password1 = forms.CharField(widget=forms.PasswordInput, label='New password')
    password2 = forms.CharField(widget=forms.PasswordInput, label='Confirm new password')

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2:
            if password1 != password2:
                self.add_error('password2', 'Passwords do not match.')
            else:
                try:
                    password_validation.validate_password(password1, user=self.user)
                except ValidationError as exc:
                    self.add_error('password1', exc)

        return cleaned_data


class ChangePasswordForm(StyledFormMixin, forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput)
    new_password1 = forms.CharField(widget=forms.PasswordInput, label='New password')
    new_password2 = forms.CharField(widget=forms.PasswordInput, label='Confirm new password')

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        old_password = self.cleaned_data['old_password']
        if not self.user.check_password(old_password):
            raise ValidationError('Your current password is incorrect.')
        return old_password

    def clean(self):
        cleaned_data = super().clean()
        new_password1 = cleaned_data.get('new_password1')
        new_password2 = cleaned_data.get('new_password2')

        if new_password1 and new_password2:
            if new_password1 != new_password2:
                self.add_error('new_password2', 'Passwords do not match.')
            else:
                try:
                    password_validation.validate_password(new_password1, user=self.user)
                except ValidationError as exc:
                    self.add_error('new_password1', exc)
            if new_password1 and self.user.check_password(new_password1):
                self.add_error('new_password1', 'Your new password must be different from your current password.')

        return cleaned_data


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_number']

    def clean_first_name(self):
        value = self.cleaned_data['first_name'].strip()
        validate_person_name(value, 'First name')
        return value.title()

    def clean_last_name(self):
        value = self.cleaned_data['last_name'].strip()
        validate_person_name(value, 'Last name')
        return value.title()

    def clean_phone_number(self):
        value = self.cleaned_data['phone_number'].strip()
        digits_only = re.sub(r'\D', '', value)
        if digits_only and not (9 <= len(digits_only) <= 15):
            raise ValidationError('Enter a valid phone number (9 to 15 digits).')
        return value


class ProfilePhotoForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['profile_photo']

    def clean_profile_photo(self):
        from apps.core.validators import validate_image_upload
        return validate_image_upload(self.cleaned_data.get('profile_photo'))


class AccountDeletionForm(StyledFormMixin, forms.Form):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm = forms.BooleanField(label='I understand this will deactivate my account.')

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data['password']
        if not self.user.check_password(password):
            raise ValidationError('Incorrect password.')
        return password
