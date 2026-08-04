"""
Sends a reminder email for every confirmed booking scheduled for
tomorrow that hasn't already received one.

This project has no background task runner (no Celery in the approved
stack), so "reminder emails" are implemented the same way most Django
projects without one do it: a management command meant to be triggered
by an external scheduler. In production, wire this into a daily cron job
or systemd timer -- see docs/DEPLOYMENT.md for the exact unit file.

Usage:
    python manage.py send_booking_reminders
    python manage.py send_booking_reminders --dry-run
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.bookings.emails import send_booking_reminder_email
from apps.bookings.models import Booking, BookingStatus


class Command(BaseCommand):
    help = 'Sends reminder emails for bookings scheduled for tomorrow.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='List which bookings would receive a reminder without actually sending anything.',
        )

    def handle(self, *args, **options):
        tomorrow = timezone.localdate() + timezone.timedelta(days=1)
        dry_run = options['dry_run']

        candidates = Booking.objects.filter(
            scheduled_date=tomorrow,
            status=BookingStatus.CONFIRMED,
            reminder_email_sent_at__isnull=True,
        ).select_related('customer', 'vehicle', 'service')

        sent_count = 0
        skipped_no_email = 0

        for booking in candidates:
            if not booking.customer.email:
                skipped_no_email += 1
                continue

            if dry_run:
                self.stdout.write(f'Would remind {booking.customer.full_name} ({booking.customer.email}) about {booking.booking_code}')
                continue

            if send_booking_reminder_email(booking):
                booking.reminder_email_sent_at = timezone.now()
                booking.save(update_fields=['reminder_email_sent_at'])
                sent_count += 1
            else:
                self.stderr.write(f'Failed to send reminder for {booking.booking_code}')

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'{candidates.count()} booking(s) would receive a reminder.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Sent {sent_count} reminder email(s). Skipped {skipped_no_email} booking(s) with no customer email on file.'
            ))
