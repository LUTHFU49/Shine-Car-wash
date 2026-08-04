import re

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ComplexPasswordValidator:
    """
    Enforces: at least one uppercase letter, one lowercase letter,
    one digit, and one special character. Combined with Django's
    built-in validators (length, similarity, common-password list,
    all-numeric check) this gives genuinely strong passwords.
    """

    def validate(self, password, user=None):
        errors = []
        if not re.search(r'[A-Z]', password):
            errors.append(_('Password must contain at least one uppercase letter.'))
        if not re.search(r'[a-z]', password):
            errors.append(_('Password must contain at least one lowercase letter.'))
        if not re.search(r'[0-9]', password):
            errors.append(_('Password must contain at least one digit.'))
        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-\[\]\\/+=~`]', password):
            errors.append(_('Password must contain at least one special character (e.g. ! @ # $ %).'))
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            'Your password must contain at least one uppercase letter, one lowercase '
            'letter, one digit, and one special character.'
        )


class PasswordReuseValidator:
    """
    Blocks reusing the current password or any of the last
    PASSWORD_HISTORY_COUNT previous ones (see apps.accounts.models.
    PasswordHistory). Only meaningful when Django's validate_password()
    is called with a `user` that already has a saved password/history --
    i.e. on change/reset, not on first registration, so it's a no-op
    there rather than an error.
    """

    def validate(self, password, user=None):
        if user is None or not user.pk or not user.password:
            return

        if user.check_password(password):
            raise ValidationError(_("You can't reuse your current password."), code='password_reused')

        from .models import PasswordHistory

        count = getattr(settings, 'PASSWORD_HISTORY_COUNT', 5)
        recent = PasswordHistory.objects.filter(user=user).order_by('-created_at')[:count]
        for entry in recent:
            if check_password(password, entry.hashed_password):
                raise ValidationError(
                    _("You can't reuse one of your last %(count)d passwords.") % {'count': count},
                    code='password_reused',
                )

    def get_help_text(self):
        count = getattr(settings, 'PASSWORD_HISTORY_COUNT', 5)
        return _('Your new password can\'t match your current password or your last %(count)d passwords.') % {'count': count}
