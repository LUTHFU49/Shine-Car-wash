import datetime

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.audit_logs.models import AuditLog
from apps.customers.models import Customer
from apps.services.models import Service, ServiceCategory
from apps.vehicles.models import Vehicle

from .models import ALLOWED_TRANSITIONS, Booking, BookingStatus, BookingType

User = get_user_model()


def make_staff_user(role=Role.MANAGER, username='staffuser'):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass1!', role=role,
    )
    user.is_email_verified = True
    user.save()
    return user


def make_customer_with_vehicle(username='bookcust', phone='0700000001', plate='KDA 900A'):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass1!', role=Role.CUSTOMER,
        first_name='Book', last_name='Customer', phone_number=phone,
    )
    customer = Customer.objects.get(user=user)
    vehicle = Vehicle.objects.create(customer=customer, license_plate=plate, make='Toyota', model='Vitz', year=2019, color='White')
    return user, customer, vehicle


def make_service(name='Basic Wash', price=500, duration=30, available_days=''):
    category = ServiceCategory.objects.create(name=f'{name} Category')
    return Service.objects.create(category=category, name=name, price=price, duration_minutes=duration, available_days=available_days)


def next_weekday(weekday_index):
    """Returns the next date (from tomorrow onward) matching the given weekday (0=Mon)."""
    today = timezone.localdate()
    days_ahead = (weekday_index - (today.weekday())) % 7
    days_ahead = days_ahead if days_ahead > 0 else 7
    return today + datetime.timedelta(days=days_ahead)


class BookingModelValidationTests(TestCase):
    def setUp(self):
        self.user, self.customer, self.vehicle = make_customer_with_vehicle()
        self.service = make_service()

    def _booking(self, **overrides):
        defaults = dict(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=timezone.localdate() + datetime.timedelta(days=1),
            scheduled_time=datetime.time(10, 0),
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        defaults.update(overrides)
        return Booking(**defaults)

    def test_valid_booking_passes_clean(self):
        booking = self._booking()
        booking.full_clean()  # should not raise

    def test_past_date_rejected(self):
        booking = self._booking(scheduled_date=timezone.localdate() - datetime.timedelta(days=1))
        with self.assertRaises(Exception):
            booking.full_clean()

    def test_time_outside_business_hours_rejected(self):
        booking = self._booking(scheduled_time=datetime.time(6, 0))
        with self.assertRaises(Exception):
            booking.full_clean()

    def test_time_at_closing_boundary_rejected(self):
        booking = self._booking(scheduled_time=datetime.time(18, 0))
        with self.assertRaises(Exception):
            booking.full_clean()

    def test_service_unavailable_on_chosen_weekday_rejected(self):
        weekend_service = make_service(name='Weekend Detail', available_days='sat,sun')
        monday = next_weekday(0)
        booking = self._booking(service=weekend_service, scheduled_date=monday, price_at_booking=weekend_service.price, duration_minutes_at_booking=weekend_service.duration_minutes)
        with self.assertRaises(Exception):
            booking.full_clean()

    def test_duplicate_vehicle_slot_rejected(self):
        first = self._booking()
        first.full_clean()
        first.save()

        second = self._booking()
        with self.assertRaises(Exception):
            second.full_clean()

    def test_booking_code_format(self):
        booking = self._booking()
        booking.full_clean()
        booking.save()
        self.assertEqual(booking.booking_code, f'BK-{booking.pk:06d}')


class BookingTransitionTests(TestCase):
    def setUp(self):
        self.user, self.customer, self.vehicle = make_customer_with_vehicle(username='transcust', phone='0700000002', plate='KDA 901A')
        self.service = make_service(name='Transition Wash')
        self.booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=timezone.localdate() + datetime.timedelta(days=1), scheduled_time=datetime.time(10, 0),
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )

    def test_pending_to_confirmed_allowed(self):
        self.assertTrue(self.booking.can_transition_to(BookingStatus.CONFIRMED))

    def test_pending_to_in_progress_not_allowed(self):
        self.assertFalse(self.booking.can_transition_to(BookingStatus.IN_PROGRESS))

    def test_completed_is_terminal(self):
        self.booking.status = BookingStatus.COMPLETED
        self.booking.save()
        self.assertEqual(ALLOWED_TRANSITIONS[BookingStatus.COMPLETED], set())
        self.assertTrue(self.booking.is_terminal)

    def test_transition_to_invalid_status_raises(self):
        with self.assertRaises(Exception):
            self.booking.transition_to(BookingStatus.COMPLETED)

    def test_transition_to_cancelled_sets_cancelled_at(self):
        self.booking.transition_to(BookingStatus.CANCELLED)
        self.assertIsNotNone(self.booking.cancelled_at)


class CustomerBookingFlowTests(TestCase):
    def setUp(self):
        self.user, self.customer, self.vehicle = make_customer_with_vehicle(username='flowcust', phone='0700000003', plate='KDA 902A')
        self.service = make_service(name='Flow Wash')
        self.client.login(username='flowcust', password='StrongPass1!')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_create_booking_starts_pending_and_sends_email(self):
        mail.outbox.clear()
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        response = self.client.post(reverse('bookings:my_create'), {
            'vehicle': self.vehicle.pk, 'service': self.service.pk,
            'scheduled_date': tomorrow.isoformat(), 'scheduled_time': '10:00',
        }, follow=True)
        booking = Booking.objects.get(customer=self.customer)
        self.assertEqual(booking.status, BookingStatus.PENDING)
        self.assertEqual(booking.booking_type, BookingType.ONLINE)
        self.assertEqual(booking.price_at_booking, self.service.price)
        self.assertTrue(any('Booking Received' in m.subject for m in mail.outbox))

    def test_cannot_book_another_customers_vehicle(self):
        _, other_customer, other_vehicle = make_customer_with_vehicle(username='othercust', phone='0700000004', plate='KDA 903A')
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        response = self.client.post(reverse('bookings:my_create'), {
            'vehicle': other_vehicle.pk, 'service': self.service.pk,
            'scheduled_date': tomorrow.isoformat(), 'scheduled_time': '10:00',
        })
        self.assertFalse(Booking.objects.filter(vehicle=other_vehicle).exists())

    def test_reschedule_own_pending_booking(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0),
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        new_date = tomorrow + datetime.timedelta(days=1)
        response = self.client.post(reverse('bookings:my_reschedule', args=[booking.public_id]), {
            'scheduled_date': new_date.isoformat(), 'scheduled_time': '11:00',
        }, follow=True)
        booking.refresh_from_db()
        self.assertEqual(booking.scheduled_date, new_date)
        self.assertEqual(booking.scheduled_time, datetime.time(11, 0))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_cancel_own_booking_sends_email(self):
        mail.outbox.clear()
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0),
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        response = self.client.post(reverse('bookings:my_cancel', args=[booking.public_id]), {'reason': 'Change of plans'}, follow=True)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertEqual(booking.cancellation_reason, 'Change of plans')
        self.assertTrue(any('Cancelled' in m.subject for m in mail.outbox))

    def test_cannot_reschedule_completed_booking(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0), status=BookingStatus.COMPLETED,
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        response = self.client.get(reverse('bookings:my_reschedule', args=[booking.public_id]), follow=True)
        self.assertContains(response, 'can no longer be rescheduled')

    def test_customer_without_vehicle_redirected_to_add_one(self):
        newcust_user = User.objects.create_user(
            username='novehicle', email='novehicle@example.com', password='StrongPass1!',
            role=Role.CUSTOMER, phone_number='0700000005',
        )
        self.client.login(username='novehicle', password='StrongPass1!')
        response = self.client.get(reverse('bookings:my_create'), follow=True)
        self.assertContains(response, 'Add a vehicle')


class StaffBookingFlowTests(TestCase):
    def setUp(self):
        self.staff = make_staff_user()
        self.user, self.customer, self.vehicle = make_customer_with_vehicle(username='staffbookcust', phone='0700000006', plate='KDA 904A')
        self.service = make_service(name='Staff Wash')
        self.client.login(username='staffuser', password='StrongPass1!')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_walk_in_booking_starts_confirmed_and_sends_email(self):
        mail.outbox.clear()
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        response = self.client.post(
            reverse('bookings:create') + f'?customer={self.customer.public_id}', {
                'vehicle': self.vehicle.pk, 'service': self.service.pk, 'customer': str(self.customer.public_id),
                'scheduled_date': tomorrow.isoformat(), 'scheduled_time': '10:00',
            }, follow=True,
        )
        booking = Booking.objects.get(customer=self.customer)
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)
        self.assertEqual(booking.booking_type, BookingType.WALK_IN)
        self.assertEqual(booking.created_by, self.staff)
        self.assertTrue(any('Confirmed' in m.subject for m in mail.outbox))

    def test_create_without_customer_selection_fails(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        response = self.client.post(reverse('bookings:create'), {
            'vehicle': self.vehicle.pk, 'service': self.service.pk,
            'scheduled_date': tomorrow.isoformat(), 'scheduled_time': '10:00',
        })
        self.assertFalse(Booking.objects.exists())

    def test_approve_pending_booking_sends_confirmation(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0),
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        with self.settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            mail.outbox.clear()
            self.client.post(reverse('bookings:set_status', args=[booking.public_id, 'confirmed']))
            booking.refresh_from_db()
            self.assertEqual(booking.status, BookingStatus.CONFIRMED)
            self.assertIsNotNone(booking.confirmation_email_sent_at)
            self.assertTrue(any('Confirmed' in m.subject for m in mail.outbox))

    def test_full_queue_lifecycle(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0), status=BookingStatus.CONFIRMED,
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        self.client.post(reverse('bookings:set_status', args=[booking.public_id, 'in_queue']))
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.IN_QUEUE)

        self.client.post(reverse('bookings:set_status', args=[booking.public_id, 'in_progress']))
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.IN_PROGRESS)

        self.client.post(reverse('bookings:set_status', args=[booking.public_id, 'completed']))
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.COMPLETED)

    def test_invalid_transition_shows_error_not_crash(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0), status=BookingStatus.COMPLETED,
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        response = self.client.post(reverse('bookings:set_status', args=[booking.public_id, 'in_queue']), follow=True)
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.COMPLETED)

    def test_staff_cancel_with_reason(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0), status=BookingStatus.CONFIRMED,
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        response = self.client.post(reverse('bookings:cancel', args=[booking.public_id]), {'reason': 'Equipment failure'}, follow=True)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertEqual(booking.cancelled_by, self.staff)

    def test_cancelled_booking_detail_page_renders_without_error(self):
        # Regression test: the detail template used to chain
        # `cancelled_by.get_full_name|default:cancelled_by.username` --
        # Django evaluates a filter's argument eagerly even when unused,
        # which crashed whenever cancelled_by needed a fallback path.
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0), status=BookingStatus.CONFIRMED,
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        response = self.client.post(reverse('bookings:cancel', args=[booking.public_id]), {'reason': 'Testing'}, follow=True)
        detail_response = self.client.get(reverse('bookings:detail', args=[booking.public_id]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Testing')

    def test_calendar_view_loads(self):
        response = self.client.get(reverse('bookings:calendar'))
        self.assertEqual(response.status_code, 200)

    def test_queue_redirects_to_today(self):
        response = self.client.get(reverse('bookings:queue'))
        self.assertEqual(response.status_code, 302)
        today = timezone.localdate().isoformat()
        self.assertIn(today, response.url)

    def test_day_view_shows_bookings(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0), status=BookingStatus.CONFIRMED,
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        response = self.client.get(reverse('bookings:day', args=[tomorrow.isoformat()]))
        self.assertContains(response, 'Staff Wash')

    def test_day_view_excludes_cancelled(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0), status=BookingStatus.CANCELLED,
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        response = self.client.get(reverse('bookings:day', args=[tomorrow.isoformat()]))
        self.assertContains(response, 'Nothing scheduled')


class BookingPermissionTests(TestCase):
    def setUp(self):
        self.user, self.customer, self.vehicle = make_customer_with_vehicle(username='permcust', phone='0700000007', plate='KDA 905A')
        self.service = make_service(name='Perm Wash')
        self.booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=timezone.localdate() + datetime.timedelta(days=1), scheduled_time=datetime.time(10, 0),
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )

    def test_anonymous_redirected_from_staff_list(self):
        response = self.client.get(reverse('bookings:list'))
        self.assertEqual(response.status_code, 302)

    def test_customer_blocked_from_staff_list(self):
        self.client.login(username='permcust', password='StrongPass1!')
        response = self.client.get(reverse('bookings:list'))
        self.assertEqual(response.status_code, 403)

    def test_customer_cannot_view_another_customers_booking(self):
        _, other_customer, _ = make_customer_with_vehicle(username='othercust2', phone='0700000008', plate='KDA 906A')
        self.client.login(username='othercust2', password='StrongPass1!')
        response = self.client.get(reverse('bookings:my_detail', args=[self.booking.public_id]))
        self.assertEqual(response.status_code, 404)

    def test_cashier_can_manage_queue(self):
        make_staff_user(role=Role.CASHIER, username='cashqueue')
        self.client.login(username='cashqueue', password='StrongPass1!')
        response = self.client.get(reverse('bookings:list'))
        self.assertEqual(response.status_code, 200)


class BookingSearchAndExportTests(TestCase):
    def setUp(self):
        make_staff_user()
        self.client.login(username='staffuser', password='StrongPass1!')
        self.user, self.customer, self.vehicle = make_customer_with_vehicle(username='searchcust', phone='0700000009', plate='KDA 907A')
        self.service = make_service(name='Search Wash')
        self.booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=timezone.localdate() + datetime.timedelta(days=1), scheduled_time=datetime.time(10, 0),
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )

    def test_search_by_customer_name(self):
        response = self.client.get(reverse('bookings:list'), {'q': 'Book Customer'})
        self.assertContains(response, 'Search Wash')

    def test_search_by_full_name_two_words_matches_split_fields(self):
        # Regression test: a search for "First Last" used to fail because
        # the whole two-word string was matched against first_name and
        # last_name individually rather than term-by-term.
        response = self.client.get(reverse('bookings:list'), {'q': 'Book Customer'})
        self.assertContains(response, 'Search Wash')
        response = self.client.get(reverse('bookings:list'), {'q': 'Nonexistent Person'})
        self.assertNotContains(response, 'Search Wash')

    def test_search_by_plate(self):
        response = self.client.get(reverse('bookings:list'), {'q': 'KDA 907A'})
        self.assertContains(response, 'Search Wash')

    def test_filter_by_status(self):
        response = self.client.get(reverse('bookings:list'), {'status': 'confirmed'})
        self.assertNotContains(response, 'Search Wash')  # booking is pending, not confirmed

    def test_csv_export(self):
        response = self.client.get(reverse('bookings:export_csv'))
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('KDA 907A', response.content.decode())

    def test_excel_export(self):
        response = self.client.get(reverse('bookings:export_excel'))
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )


class SendBookingRemindersCommandTests(TestCase):
    def setUp(self):
        self.user, self.customer, self.vehicle = make_customer_with_vehicle(username='remindcust', phone='0700000010', plate='KDA 908A')
        self.service = make_service(name='Reminder Wash')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_sends_reminder_for_tomorrows_confirmed_booking(self):
        from django.core.management import call_command

        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0), status=BookingStatus.CONFIRMED,
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        mail.outbox.clear()
        call_command('send_booking_reminders')

        booking.refresh_from_db()
        self.assertIsNotNone(booking.reminder_email_sent_at)
        self.assertTrue(any('Reminder' in m.subject for m in mail.outbox))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_does_not_double_send(self):
        from django.core.management import call_command

        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0), status=BookingStatus.CONFIRMED,
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        call_command('send_booking_reminders')
        mail.outbox.clear()
        call_command('send_booking_reminders')
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_does_not_remind_bookings_further_out(self):
        from django.core.management import call_command

        next_week = timezone.localdate() + datetime.timedelta(days=7)
        Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=next_week, scheduled_time=datetime.time(10, 0), status=BookingStatus.CONFIRMED,
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        mail.outbox.clear()
        call_command('send_booking_reminders')
        self.assertEqual(len(mail.outbox), 0)

    def test_dry_run_does_not_send_or_mark(self):
        from django.core.management import call_command

        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        booking = Booking.objects.create(
            customer=self.customer, vehicle=self.vehicle, service=self.service,
            scheduled_date=tomorrow, scheduled_time=datetime.time(10, 0), status=BookingStatus.CONFIRMED,
            price_at_booking=self.service.price, duration_minutes_at_booking=self.service.duration_minutes,
        )
        call_command('send_booking_reminders', '--dry-run')
        booking.refresh_from_db()
        self.assertIsNone(booking.reminder_email_sent_at)
