"""
All money-moving logic lives here, same rationale as
apps.inventory.services: Invoice.amount_paid/status must never drift
from the sum of COMPLETED Payments minus COMPLETED Refunds, no matter
which caller (a view, the M-Pesa callback, a management command)
triggers the change.
"""
from datetime import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.urls import reverse
from django.utils import timezone

from . import daraja
from .models import Invoice, InvoiceStatus, Payment, PaymentMethod, PaymentStatus, Refund, RefundStatus


# ============================================================
# Invoices
# ============================================================

def get_or_create_invoice_for_booking(booking):
    """Idempotent: a booking only ever gets one invoice, created the
    first time it's confirmed (see apps.payments.signals)."""
    existing = Invoice.objects.filter(booking=booking).first()
    if existing:
        return existing

    from django.conf import settings as django_settings

    subtotal = booking.price_at_booking
    tax_rate = django_settings.INVOICE_TAX_RATE
    tax_amount = (subtotal * tax_rate / Decimal('100')).quantize(Decimal('0.01'))
    total_amount = subtotal + tax_amount

    return Invoice.objects.create(
        booking=booking, subtotal=subtotal, tax_rate=tax_rate,
        tax_amount=tax_amount, total_amount=total_amount, created_by=booking.created_by,
    )


def void_invoice(invoice, user):
    if invoice.amount_paid > 0:
        raise ValidationError('An invoice with payments recorded against it cannot be voided -- refund the payments first.')
    invoice.status = InvoiceStatus.VOID
    invoice.save(update_fields=['status', 'updated_at'])
    return invoice


def _sync_invoice_status(invoice_id):
    invoice = Invoice.objects.get(pk=invoice_id)
    if invoice.status == InvoiceStatus.VOID:
        return invoice
    if invoice.amount_paid <= 0:
        new_status = InvoiceStatus.UNPAID
    elif invoice.amount_paid < invoice.total_amount:
        new_status = InvoiceStatus.PARTIALLY_PAID
    else:
        new_status = InvoiceStatus.PAID
    if new_status != invoice.status:
        Invoice.objects.filter(pk=invoice_id).update(status=new_status)
    return Invoice.objects.get(pk=invoice_id)


# ============================================================
# Notifications / receipts
# ============================================================

def _notify_payment_completed(payment):
    from apps.notifications.utils import notify
    from apps.notifications.models import NotificationLevel
    from apps.accounts.emails import send_branded_email
    from .reports import payment_receipt_pdf_bytes

    invoice = payment.invoice
    customer_user = invoice.booking.customer.user

    # Walk-in customers (registered by staff at the counter) have no login
    # account at all -- customer.user is None by design (see
    # apps.customers.models.Customer docstring). There's no account to
    # notify or email in that case, so we just skip both silently rather
    # than crash the whole payment-recording transaction.
    if customer_user is None:
        return

    detail_url = reverse('payments:my_payment_status', args=[payment.public_id])
    notify(
        customer_user, title='Payment received',
        message=f'KSh {payment.amount:,.2f} received for {invoice.booking.booking_code}. Balance: KSh {invoice.balance:,.2f}.',
        level=NotificationLevel.SUCCESS, url=detail_url,
    )

    if customer_user.email:
        pdf_bytes = payment_receipt_pdf_bytes(payment)
        send_branded_email(
            subject=f'Receipt for {payment.reference_code}',
            template_name='payment_receipt_email.html',
            context={'user': customer_user, 'payment': payment, 'invoice': invoice},
            to_email=customer_user.email,
            attachments=[(f'{payment.reference_code}.pdf', pdf_bytes, 'application/pdf')],
        )


def _notify_payment_failed(payment):
    from apps.notifications.utils import notify
    from apps.notifications.models import NotificationLevel

    recipient = payment.initiated_by or payment.invoice.booking.customer.user
    notify(
        recipient, title='Payment failed',
        message=f'{payment.get_method_display()} payment of KSh {payment.amount:,.2f} for '
                 f'{payment.invoice.booking.booking_code} did not go through: {payment.result_description or "please try again."}',
        level=NotificationLevel.DANGER,
        url=reverse('payments:payment_detail', args=[payment.public_id]),
    )


def _notify_refund(refund):
    from apps.notifications.utils import notify
    from apps.notifications.models import NotificationLevel
    from apps.accounts.emails import send_branded_email

    invoice = refund.payment.invoice
    customer_user = invoice.booking.customer.user

    # Same walk-in case as _notify_payment_completed above -- no account to
    # notify or email, so skip rather than crash the refund transaction.
    if customer_user is None:
        return

    notify(
        customer_user, title='Refund processed',
        message=f'KSh {refund.amount:,.2f} refunded for {invoice.booking.booking_code}.',
        level=NotificationLevel.INFO,
        url=reverse('payments:payment_detail', args=[refund.payment.public_id]),
    )
    if customer_user.email:
        send_branded_email(
            subject=f'Refund confirmation — {refund.reference_code}',
            template_name='refund_processed_email.html',
            context={'user': customer_user, 'refund': refund, 'invoice': invoice},
            to_email=customer_user.email,
        )


def _apply_completed_payment(payment):
    Invoice.objects.filter(pk=payment.invoice_id).update(amount_paid=F('amount_paid') + payment.amount)
    _sync_invoice_status(payment.invoice_id)
    _notify_payment_completed(payment)


# ============================================================
# Cash payments
# ============================================================

def record_cash_payment(invoice, amount, user, notes=''):
    if invoice.status == InvoiceStatus.VOID:
        raise ValidationError('This invoice has been voided.')
    if amount <= 0:
        raise ValidationError('Amount must be greater than zero.')
    if amount > invoice.balance:
        raise ValidationError(f'Amount exceeds the outstanding balance of KSh {invoice.balance:,.2f}.')

    with transaction.atomic():
        payment = Payment.objects.create(
            invoice=invoice, method=PaymentMethod.CASH, amount=amount,
            status=PaymentStatus.COMPLETED, notes=notes,
            initiated_by=user, completed_at=timezone.now(),
        )
        _apply_completed_payment(payment)

    return payment


def record_wallet_payment(invoice, amount, user, notes=''):
    """Same shape as record_cash_payment -- the money has already left
    the customer's loyalty wallet by the time this is called (see
    apps.loyalty.services.pay_with_wallet, which debits the wallet
    first and calls this to record the Payment/Invoice side)."""
    if invoice.status == InvoiceStatus.VOID:
        raise ValidationError('This invoice has been voided.')
    if amount <= 0:
        raise ValidationError('Amount must be greater than zero.')
    if amount > invoice.balance:
        raise ValidationError(f'Amount exceeds the outstanding balance of KSh {invoice.balance:,.2f}.')

    with transaction.atomic():
        payment = Payment.objects.create(
            invoice=invoice, method=PaymentMethod.WALLET, amount=amount,
            status=PaymentStatus.COMPLETED, notes=notes,
            initiated_by=user, completed_at=timezone.now(),
        )
        _apply_completed_payment(payment)

    return payment


def apply_discount(invoice, discount_amount, reason=''):
    """Reduces an invoice's total_amount by a loyalty discount (a
    coupon or an automatic tier discount -- see
    apps.loyalty.services). Never lets the total drop below what's
    already been paid against it, and re-syncs status the same way
    every other total_amount-affecting change does."""
    if invoice.status == InvoiceStatus.VOID:
        raise ValidationError('This invoice has been voided.')
    if discount_amount <= 0:
        raise ValidationError('Discount amount must be greater than zero.')
    if discount_amount > (invoice.total_amount - invoice.amount_paid):
        raise ValidationError('Discount cannot exceed the invoice\'s outstanding balance.')

    Invoice.objects.filter(pk=invoice.pk).update(total_amount=F('total_amount') - discount_amount)
    return _sync_invoice_status(invoice.pk)


# ============================================================
# M-Pesa payments
# ============================================================

def initiate_mpesa_payment(invoice, phone_number, amount, user):
    if invoice.status == InvoiceStatus.VOID:
        raise ValidationError('This invoice has been voided.')
    if amount <= 0:
        raise ValidationError('Amount must be greater than zero.')
    if amount > invoice.balance:
        raise ValidationError(f'Amount exceeds the outstanding balance of KSh {invoice.balance:,.2f}.')

    payment = Payment.objects.create(
        invoice=invoice, method=PaymentMethod.MPESA, amount=amount,
        status=PaymentStatus.PROCESSING, phone_number=phone_number, initiated_by=user,
    )

    try:
        response = daraja.stk_push(
            phone_number=phone_number, amount=amount,
            account_reference=invoice.invoice_number,
            transaction_desc=f'{invoice.booking.booking_code}',
        )
    except daraja.DarajaError as exc:
        payment.status = PaymentStatus.FAILED
        payment.result_description = str(exc)
        payment.save(update_fields=['status', 'result_description', 'updated_at'])
        raise ValidationError(str(exc)) from exc

    payment.checkout_request_id = response.get('CheckoutRequestID', '')
    payment.merchant_request_id = response.get('MerchantRequestID', '')
    payment.save(update_fields=['checkout_request_id', 'merchant_request_id', 'updated_at'])
    return payment


def _parse_mpesa_transaction_date(raw_value):
    if not raw_value:
        return None
    try:
        naive = datetime.strptime(str(raw_value), '%Y%m%d%H%M%S')
        return timezone.make_aware(naive)
    except (ValueError, TypeError):
        return None


def _apply_stk_result(payment, result_code, result_description, callback_items=None):
    """Shared by the callback handler and the manual "verify" action so
    both paths update a payment identically. Idempotent: a payment
    already resolved (not PROCESSING) is left untouched."""
    if payment.status != PaymentStatus.PROCESSING:
        return payment

    payment.result_code = str(result_code) if result_code is not None else ''
    payment.result_description = result_description or ''

    if str(result_code) == '0':
        items = {item.get('Name'): item.get('Value') for item in (callback_items or [])}
        payment.mpesa_receipt_number = items.get('MpesaReceiptNumber', '') or payment.mpesa_receipt_number
        payment.transaction_date_mpesa = _parse_mpesa_transaction_date(items.get('TransactionDate'))
        payment.status = PaymentStatus.COMPLETED
        payment.completed_at = timezone.now()
        payment.save(update_fields=[
            'result_code', 'result_description', 'mpesa_receipt_number',
            'transaction_date_mpesa', 'status', 'completed_at', 'updated_at',
        ])
        _apply_completed_payment(payment)
    else:
        payment.status = PaymentStatus.FAILED
        payment.save(update_fields=['result_code', 'result_description', 'status', 'updated_at'])
        _notify_payment_failed(payment)

    return payment


def process_mpesa_callback(payload):
    """Parses a Daraja STK callback POST body. Returns the updated
    Payment, or None if the CheckoutRequestID isn't recognized."""
    stk_callback = (payload or {}).get('Body', {}).get('stkCallback', {})
    checkout_request_id = stk_callback.get('CheckoutRequestID')
    if not checkout_request_id:
        return None

    try:
        payment = Payment.objects.select_related('invoice').get(checkout_request_id=checkout_request_id)
    except Payment.DoesNotExist:
        return None

    callback_items = stk_callback.get('CallbackMetadata', {}).get('Item', [])
    return _apply_stk_result(
        payment, stk_callback.get('ResultCode'), stk_callback.get('ResultDesc'), callback_items,
    )


def verify_mpesa_payment(payment):
    """Actively queries Daraja for a still-PROCESSING payment -- used
    when the async callback never arrived."""
    if payment.method != PaymentMethod.MPESA or payment.status != PaymentStatus.PROCESSING:
        raise ValidationError('Only a processing M-Pesa payment can be verified.')
    if not payment.checkout_request_id:
        raise ValidationError('This payment has no checkout request to verify.')

    result = daraja.stk_query(payment.checkout_request_id)
    result_code = result.get('ResultCode')
    result_desc = result.get('ResultDesc')
    return _apply_stk_result(payment, result_code, result_desc, callback_items=None)


# ============================================================
# Refunds
# ============================================================

def record_refund(payment, amount, reason, user):
    if payment.status != PaymentStatus.COMPLETED:
        raise ValidationError('Only a completed payment can be refunded.')
    if amount <= 0:
        raise ValidationError('Refund amount must be greater than zero.')
    if amount > payment.refundable_amount:
        raise ValidationError(f'Refund amount exceeds the refundable balance of KSh {payment.refundable_amount:,.2f}.')

    with transaction.atomic():
        refund = Refund.objects.create(
            payment=payment, amount=amount, reason=reason,
            status=RefundStatus.COMPLETED, processed_by=user, processed_at=timezone.now(),
        )
        Invoice.objects.filter(pk=payment.invoice_id).update(amount_paid=F('amount_paid') - amount)
        _sync_invoice_status(payment.invoice_id)

    _notify_refund(refund)
    return refund


# ============================================================
# Reporting: daily collections / revenue summary
# ============================================================

def compute_daily_collections(start_date, end_date):
    """Returns a list of {date, cash_total, mpesa_total, total} rows for
    every day with at least one completed payment in the range."""
    from django.db.models.functions import TruncDate

    rows = (
        Payment.objects.filter(status=PaymentStatus.COMPLETED, completed_at__date__range=[start_date, end_date])
        .annotate(day=TruncDate('completed_at'))
        .values('day', 'method')
        .annotate(total=Sum('amount'))
        .order_by('day')
    )

    by_day = {}
    for row in rows:
        entry = by_day.setdefault(row['day'], {'date': row['day'], 'cash_total': Decimal('0.00'), 'mpesa_total': Decimal('0.00')})
        if row['method'] == PaymentMethod.CASH:
            entry['cash_total'] = row['total']
        else:
            entry['mpesa_total'] = row['total']

    results = []
    for entry in sorted(by_day.values(), key=lambda item: item['date']):
        entry['total'] = entry['cash_total'] + entry['mpesa_total']
        results.append(entry)
    return results


def compute_revenue_summary(start_date, end_date):
    payments = Payment.objects.filter(status=PaymentStatus.COMPLETED, completed_at__date__range=[start_date, end_date])
    refunds = Refund.objects.filter(status=RefundStatus.COMPLETED, processed_at__date__range=[start_date, end_date])

    gross = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    refunded = refunds.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    cash_total = payments.filter(method=PaymentMethod.CASH).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    mpesa_total = payments.filter(method=PaymentMethod.MPESA).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    return {
        'gross_revenue': gross,
        'refunded': refunded,
        'net_revenue': gross - refunded,
        'cash_total': cash_total,
        'mpesa_total': mpesa_total,
        'transaction_count': payments.count(),
    }
