from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.audit_logs.models import AuditLog

from .emails import send_verification_email, send_welcome_email
from .models import EmailVerificationToken, Role, User


@receiver(post_save, sender=User)
def handle_new_user_registered(sender, instance, created, **kwargs):
    """
    Fires once, exactly when a User row is first created (not on every
    subsequent save/update). Creates the one-time email verification
    token, emails the verification link, sends the welcome email, records
    the registration in the audit trail, and -- for Customer-role users --
    auto-creates the linked Customer profile the Customers app manages.
    """
    if not created:
        return

    expires_at = timezone.now() + timedelta(hours=2)
    token = EmailVerificationToken.objects.create(user=instance, expires_at=expires_at)

    verification_path = reverse('accounts:verify_email', kwargs={'token': str(token.token)})

    # Signals don't get the request object, so we build the absolute URL
    # from SITE_DOMAIN in settings rather than request.build_absolute_uri().
    from django.conf import settings
    scheme = 'http' if settings.DEBUG else 'https'
    verification_url = f'{scheme}://{settings.SITE_DOMAIN}{verification_path}'

    send_verification_email(instance, verification_url)
    send_welcome_email(instance)

    AuditLog.objects.create(
        user=instance,
        action=AuditLog.Action.CREATE,
        model_name='User',
        object_id=str(instance.pk),
        description=f'New account registered: {instance.username}',
    )

    if instance.role == Role.CUSTOMER:
        # Imported here (not at module level) to avoid a circular import:
        # apps.customers isn't guaranteed to be fully loaded yet when
        # apps.accounts' AppConfig.ready() wires up this signal.
        from apps.customers.models import Customer

        if instance.phone_number and not Customer.objects.filter(phone_number=instance.phone_number).exists():
            customer = Customer.objects.create(
                user=instance,
                first_name=instance.first_name,
                last_name=instance.last_name,
                email=instance.email,
                phone_number=instance.phone_number,
            )
            AuditLog.objects.create(
                user=instance, action=AuditLog.Action.CREATE, model_name='Customer',
                object_id=str(customer.pk),
                description=f'Customer profile auto-created from self-registration: {customer.full_name}',
            )
