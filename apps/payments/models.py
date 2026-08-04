import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class PaymentMethod(models.TextChoices):
    CASH = 'cash', 'Cash'
    MPESA = 'mpesa', 'M-Pesa'
    WALLET = 'wallet', 'Loyalty Wallet'


class PaymentStatus(models.TextChoices):
    PROCESSING = 'processing', 'Processing'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    CANCELLED = 'cancelled', 'Cancelled'


class InvoiceStatus(models.TextChoices):
    UNPAID = 'unpaid', 'Unpaid'
    PARTIALLY_PAID = 'partially_paid', 'Partially Paid'
    PAID = 'paid', 'Paid'
    VOID = 'void', 'Void'


class RefundStatus(models.TextChoices):
    COMPLETED = 'completed', 'Completed'
    REJECTED = 'rejected', 'Rejected'


class Invoice(models.Model):
    """
    One invoice per Booking, created automatically the first time a
    booking is confirmed (see apps.payments.signals) -- mirrors the
    timing apps.inventory uses for stock reservation. `amount_paid` and
    `status` are denormalized and maintained exclusively by
    apps.payments.services as Payments/Refunds are recorded.
    """
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    booking = models.OneToOneField('bookings.Booking', on_delete=models.PROTECT, related_name='invoice')

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text='Percentage, snapshotted at issue time.')
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), editable=False)

    status = models.CharField(max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.UNPAID, db_index=True)
    issued_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices_created',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments_invoice'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.invoice_number} — {self.booking.booking_code}'

    @property
    def invoice_number(self):
        return f'INV-{self.pk:06d}' if self.pk else 'INV-PENDING'

    @property
    def balance(self):
        return max(self.total_amount - self.amount_paid, Decimal('0.00'))

    @property
    def is_fully_paid(self):
        return self.status == InvoiceStatus.PAID


class Payment(models.Model):
    """
    One payment attempt/transaction against an Invoice. A single
    invoice can have several Payment rows (a failed STK push followed
    by a successful cash payment, or two partial cash payments) --
    Invoice.amount_paid is the running total of COMPLETED ones.
    """
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')

    method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(1)])
    status = models.CharField(max_length=15, choices=PaymentStatus.choices, default=PaymentStatus.PROCESSING, db_index=True)

    # M-Pesa / Daraja fields -- populated by apps.payments.daraja + services
    phone_number = models.CharField(max_length=15, blank=True)
    checkout_request_id = models.CharField(max_length=60, blank=True, db_index=True)
    merchant_request_id = models.CharField(max_length=60, blank=True)
    mpesa_receipt_number = models.CharField(max_length=30, blank=True, db_index=True)
    result_code = models.CharField(max_length=10, blank=True)
    result_description = models.CharField(max_length=255, blank=True)
    transaction_date_mpesa = models.DateTimeField(blank=True, null=True)

    notes = models.CharField(max_length=255, blank=True)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments_initiated',
        help_text='Whoever triggered this payment -- a customer for self-service M-Pesa, or the staff member for cash / counter M-Pesa.',
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'payments_payment'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', '-created_at'])]

    def __str__(self):
        return f'{self.reference_code} — {self.get_method_display()} KSh {self.amount}'

    @property
    def reference_code(self):
        return f'PAY-{self.pk:06d}' if self.pk else 'PAY-PENDING'

    @property
    def refunded_amount(self):
        return sum((r.amount for r in self.refunds.filter(status=RefundStatus.COMPLETED)), start=Decimal('0.00'))

    @property
    def refundable_amount(self):
        if self.status != PaymentStatus.COMPLETED:
            return Decimal('0.00')
        return max(self.amount - self.refunded_amount, Decimal('0.00'))


class Refund(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='refunds')

    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(1)])
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=RefundStatus.choices, default=RefundStatus.COMPLETED, db_index=True)

    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='refunds_processed',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'payments_refund'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference_code} — KSh {self.amount} for {self.payment.reference_code}'

    @property
    def reference_code(self):
        return f'REF-{self.pk:06d}' if self.pk else 'REF-PENDING'
