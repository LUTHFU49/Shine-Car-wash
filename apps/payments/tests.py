import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.bookings.models import Booking, BookingStatus
from apps.customers.models import Customer
from apps.services.models import Service, ServiceCategory
from apps.vehicles.models import Vehicle

from . import services
from .models import Invoice, InvoiceStatus, Payment, PaymentMethod, PaymentStatus, Refund

User = get_user_model()


def make_staff_user(role=Role.MANAGER, username='paystaff'):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass1!', role=role,
    )
    user.is_email_verified = True
    user.save()
    return user


def make_customer_with_vehicle(username='paycust', phone='0711000001', plate='KDB 900A'):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='StrongPass1!', role=Role.CUSTOMER,
        first_name='Pay', last_name='Customer', phone_number=phone,
    )
    customer = Customer.objects.get(user=user)
    vehicle = Vehicle.objects.create(customer=customer, license_plate=plate, make='Toyota', model='Vitz', year=2019, color='White')
    return user, customer, vehicle


def make_confirmed_booking(customer, vehicle, price=Decimal('1000.00')):
    category = ServiceCategory.objects.create(name='Payments Test Category')
    service = Service.objects.create(category=category, name='Payments Test Wash', price=price, duration_minutes=30)
    booking = Booking.objects.create(
        customer=customer, vehicle=vehicle, service=service,
        scheduled_date=timezone.localdate() + datetime.timedelta(days=1), scheduled_time=datetime.time(10, 0),
        price_at_booking=price, duration_minutes_at_booking=30,
    )
    booking.status = BookingStatus.CONFIRMED
    booking.save()
    return booking


class InvoiceLifecycleTests(TestCase):
    def setUp(self):
        _, self.customer, self.vehicle = make_customer_with_vehicle()
        self.booking = make_confirmed_booking(self.customer, self.vehicle, price=Decimal('1000.00'))
        self.invoice = Invoice.objects.get(booking=self.booking)

    def test_invoice_auto_created_on_booking_confirmed(self):
        self.assertEqual(self.invoice.total_amount, Decimal('1000.00'))
        self.assertEqual(self.invoice.status, InvoiceStatus.UNPAID)
        self.assertEqual(self.invoice.balance, Decimal('1000.00'))

    def test_get_or_create_is_idempotent(self):
        again = services.get_or_create_invoice_for_booking(self.booking)
        self.assertEqual(again.pk, self.invoice.pk)
        self.assertEqual(Invoice.objects.filter(booking=self.booking).count(), 1)


class CashPaymentTests(TestCase):
    def setUp(self):
        self.staff = make_staff_user()
        _, self.customer, self.vehicle = make_customer_with_vehicle()
        self.booking = make_confirmed_booking(self.customer, self.vehicle, price=Decimal('1000.00'))
        self.invoice = Invoice.objects.get(booking=self.booking)

    def test_partial_cash_payment_moves_invoice_to_partially_paid(self):
        services.record_cash_payment(self.invoice, Decimal('400.00'), self.staff)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('400.00'))
        self.assertEqual(self.invoice.status, InvoiceStatus.PARTIALLY_PAID)
        self.assertEqual(self.invoice.balance, Decimal('600.00'))

    def test_full_cash_payment_marks_invoice_paid(self):
        services.record_cash_payment(self.invoice, Decimal('1000.00'), self.staff)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, InvoiceStatus.PAID)
        self.assertTrue(self.invoice.is_fully_paid)

    def test_cannot_overpay(self):
        with self.assertRaises(ValidationError):
            services.record_cash_payment(self.invoice, Decimal('1500.00'), self.staff)

    def test_cannot_pay_zero_or_negative(self):
        with self.assertRaises(ValidationError):
            services.record_cash_payment(self.invoice, Decimal('0.00'), self.staff)

    def test_cannot_pay_a_voided_invoice(self):
        services.void_invoice(self.invoice, self.staff)
        with self.assertRaises(ValidationError):
            services.record_cash_payment(self.invoice, Decimal('100.00'), self.staff)

    def test_cannot_void_invoice_with_payments(self):
        services.record_cash_payment(self.invoice, Decimal('100.00'), self.staff)
        self.invoice.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.void_invoice(self.invoice, self.staff)


class MpesaCallbackTests(TestCase):
    """The M-Pesa async callback is the highest-risk code path in this
    app -- it's an unauthenticated webhook that moves real money state,
    and Safaricom is documented to sometimes resend the same callback.
    Idempotency here isn't optional."""

    def setUp(self):
        self.staff = make_staff_user()
        _, self.customer, self.vehicle = make_customer_with_vehicle()
        self.booking = make_confirmed_booking(self.customer, self.vehicle, price=Decimal('500.00'))
        self.invoice = Invoice.objects.get(booking=self.booking)
        self.payment = Payment.objects.create(
            invoice=self.invoice, method=PaymentMethod.MPESA, amount=Decimal('500.00'),
            status=PaymentStatus.PROCESSING, phone_number='0711000001',
            checkout_request_id='ws_CO_test12345', initiated_by=self.staff,
        )

    def _success_payload(self):
        return {
            'Body': {'stkCallback': {
                'CheckoutRequestID': 'ws_CO_test12345', 'ResultCode': 0, 'ResultDesc': 'Success',
                'CallbackMetadata': {'Item': [
                    {'Name': 'MpesaReceiptNumber', 'Value': 'QAT12345XY'},
                    {'Name': 'TransactionDate', 'Value': 20260722103000},
                ]},
            }},
        }

    def test_successful_callback_completes_payment_and_invoice(self):
        services.process_mpesa_callback(self._success_payload())
        self.payment.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.COMPLETED)
        self.assertEqual(self.payment.mpesa_receipt_number, 'QAT12345XY')
        self.assertEqual(self.invoice.amount_paid, Decimal('500.00'))
        self.assertEqual(self.invoice.status, InvoiceStatus.PAID)

    def test_duplicate_callback_does_not_double_apply(self):
        services.process_mpesa_callback(self._success_payload())
        services.process_mpesa_callback(self._success_payload())  # Safaricom resend
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('500.00'))  # not 1000

    def test_failed_result_code_marks_payment_failed_without_touching_invoice(self):
        payload = self._success_payload()
        payload['Body']['stkCallback']['ResultCode'] = 1032
        payload['Body']['stkCallback']['ResultDesc'] = 'Request cancelled by user'
        services.process_mpesa_callback(payload)
        self.payment.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.FAILED)
        self.assertEqual(self.invoice.amount_paid, Decimal('0.00'))

    def test_unknown_checkout_request_id_returns_none_and_does_nothing(self):
        payload = self._success_payload()
        payload['Body']['stkCallback']['CheckoutRequestID'] = 'ws_CO_does_not_exist'
        result = services.process_mpesa_callback(payload)
        self.assertIsNone(result)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PROCESSING)  # untouched

    def test_callback_view_rejects_disallowed_ip_when_allowlist_configured(self):
        with override_settings(MPESA_CALLBACK_ALLOWED_IPS=['41.90.0.1']):
            response = self.client.post(
                reverse('payments:mpesa_callback'), data=self._success_payload(),
                content_type='application/json', REMOTE_ADDR='1.2.3.4',
            )
        self.assertEqual(response.status_code, 403)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PROCESSING)  # rejected before processing

    def test_callback_view_accepts_allowlisted_ip(self):
        with override_settings(MPESA_CALLBACK_ALLOWED_IPS=['9.9.9.9']):
            response = self.client.post(
                reverse('payments:mpesa_callback'), data=self._success_payload(),
                content_type='application/json', REMOTE_ADDR='9.9.9.9',
            )
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.COMPLETED)

    def test_callback_view_open_when_allowlist_not_configured(self):
        response = self.client.post(
            reverse('payments:mpesa_callback'), data=self._success_payload(),
            content_type='application/json', REMOTE_ADDR='203.0.113.7',
        )
        self.assertEqual(response.status_code, 200)


class RefundTests(TestCase):
    def setUp(self):
        self.staff = make_staff_user()
        _, self.customer, self.vehicle = make_customer_with_vehicle()
        self.booking = make_confirmed_booking(self.customer, self.vehicle, price=Decimal('800.00'))
        self.invoice = Invoice.objects.get(booking=self.booking)
        self.payment = services.record_cash_payment(self.invoice, Decimal('800.00'), self.staff)

    def test_full_refund_reverts_invoice_to_unpaid(self):
        services.record_refund(self.payment, Decimal('800.00'), 'Customer complaint', self.staff)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('0.00'))
        self.assertEqual(self.invoice.status, InvoiceStatus.UNPAID)

    def test_partial_refund_reverts_invoice_to_partially_paid(self):
        services.record_refund(self.payment, Decimal('300.00'), 'Partial goodwill refund', self.staff)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('500.00'))
        self.assertEqual(self.invoice.status, InvoiceStatus.PARTIALLY_PAID)

    def test_cannot_refund_more_than_paid(self):
        with self.assertRaises(ValidationError):
            services.record_refund(self.payment, Decimal('900.00'), 'Too much', self.staff)

    def test_cannot_double_refund_beyond_refundable_amount(self):
        services.record_refund(self.payment, Decimal('500.00'), 'First refund', self.staff)
        self.payment.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.record_refund(self.payment, Decimal('400.00'), 'Second refund too much', self.staff)

    def test_cannot_refund_a_non_completed_payment(self):
        processing_payment = Payment.objects.create(
            invoice=self.invoice, method=PaymentMethod.MPESA, amount=Decimal('100.00'), status=PaymentStatus.PROCESSING,
        )
        with self.assertRaises(ValidationError):
            services.record_refund(processing_payment, Decimal('50.00'), 'Nope', self.staff)


class PaymentViewRBACTests(TestCase):
    def setUp(self):
        self.manager = make_staff_user(role=Role.MANAGER, username='paymgr')
        self.employee = make_staff_user(role=Role.EMPLOYEE, username='payemp')
        _, self.customer, self.vehicle = make_customer_with_vehicle()
        self.booking = make_confirmed_booking(self.customer, self.vehicle, price=Decimal('600.00'))
        self.invoice = Invoice.objects.get(booking=self.booking)
        self.payment = services.record_cash_payment(self.invoice, Decimal('600.00'), self.manager)

    def test_employee_cannot_issue_refund(self):
        self.client.login(username='payemp', password='StrongPass1!')
        response = self.client.post(
            reverse('payments:payment_refund', args=[self.payment.public_id]),
            {'amount': '100', 'reason': 'test'},
        )
        self.assertEqual(response.status_code, 403)

    def test_manager_can_issue_refund(self):
        self.client.login(username='paymgr', password='StrongPass1!')
        response = self.client.post(
            reverse('payments:payment_refund', args=[self.payment.public_id]),
            {'amount': '100', 'reason': 'test refund'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Refund.objects.filter(payment=self.payment).count(), 1)

    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse('payments:payment_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)
