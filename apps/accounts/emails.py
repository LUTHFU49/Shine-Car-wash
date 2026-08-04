"""
Central place for every outgoing ShineHub email. Each email is rendered
from an HTML template (with a plain-text fallback derived from it) and
sent via EmailMultiAlternatives so it degrades gracefully in clients
that don't render HTML.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger('shinehub')


def send_branded_email(subject, template_name, context, to_email, attachments=None):
    """
    Renders templates/emails/<template_name> with the given context
    (plus global brand context) and sends it to `to_email`. Returns
    True on success, False on failure — callers decide whether a
    failed send should block the calling request or just be logged.

    `attachments`, if given, is an iterable of (filename, content,
    mimetype) tuples -- e.g. a payment receipt PDF. Optional and
    backward compatible: every existing caller that doesn't pass it
    behaves exactly as before.
    """
    context = {
        'SITE_NAME': settings.SITE_NAME,
        'COMPANY_NAME': settings.COMPANY_NAME,
        'SITE_DOMAIN': settings.SITE_DOMAIN,
        **context,
    }

    try:
        html_body = render_to_string(f'emails/{template_name}', context)
        text_body = strip_tags(html_body)

        message = EmailMultiAlternatives(
            subject=f'{subject} — {settings.SITE_NAME}',
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        message.attach_alternative(html_body, 'text/html')
        for filename, content, mimetype in (attachments or []):
            message.attach(filename, content, mimetype)
        message.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('Failed to send "%s" email to %s', template_name, to_email)
        return False


def send_welcome_email(user):
    return send_branded_email(
        subject='Welcome to ShineHub',
        template_name='welcome_email.html',
        context={'user': user},
        to_email=user.email,
    )


def send_verification_email(user, verification_url):
    return send_branded_email(
        subject='Verify your email address',
        template_name='verification_email.html',
        context={'user': user, 'verification_url': verification_url},
        to_email=user.email,
    )


def send_password_reset_email(user, reset_url):
    return send_branded_email(
        subject='Reset your password',
        template_name='password_reset_email.html',
        context={'user': user, 'reset_url': reset_url},
        to_email=user.email,
    )


def send_password_changed_email(user):
    return send_branded_email(
        subject='Your password was changed',
        template_name='password_changed_email.html',
        context={'user': user},
        to_email=user.email,
    )


def send_account_deactivated_email(user):
    return send_branded_email(
        subject='Your account has been deactivated',
        template_name='account_deactivated_email.html',
        context={'user': user},
        to_email=user.email,
    )


def send_new_device_login_email(user, ip_address, user_agent, when):
    return send_branded_email(
        subject='New login to your account',
        template_name='new_device_login_email.html',
        context={'user': user, 'ip_address': ip_address, 'user_agent': user_agent, 'when': when},
        to_email=user.email,
    )
