import json
from datetime import timedelta
from ipaddress import ip_address, ip_network

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from apps.audit_logs.models import AuditLog
from apps.core.decorators import customer_required, management_required, staff_required
from apps.customers.models import Customer

from . import daraja, services
from .forms import CashPaymentForm, CollectionsRangeForm, MpesaPaymentForm, RefundForm, TransactionSearchForm
from .models import Invoice, InvoiceStatus, Payment, PaymentStatus
from .reports import (
    collections_csv_response, invoice_pdf_response, payment_receipt_pdf_response,
    transactions_csv_response, transactions_excel_response,
)

PAGE_SIZE = 20


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log(request, action, model_name, obj, description):
    AuditLog.objects.create(
        user=request.user, action=action, model_name=model_name,
        object_id=str(obj.pk), description=description, ip_address=_client_ip(request),
    )


def _get_own_customer_profile(request):
    return Customer.objects.filter(user=request.user).first()


def _is_allowed_mpesa_ip(ip):
    """
    True if settings.MPESA_CALLBACK_ALLOWED_IPS is empty (allowlist not
    configured -- correct default for sandbox) or `ip` matches one of
    the configured entries, which may be bare IPs or CIDR ranges.
    """
    allowlist = settings.MPESA_CALLBACK_ALLOWED_IPS
    if not allowlist:
        return True
    try:
        candidate = ip_address(ip)
    except ValueError:
        return False
    for entry in allowlist:
        try:
            if '/' in entry:
                if candidate in ip_network(entry, strict=False):
                    return True
            elif candidate == ip_address(entry):
                return True
        except ValueError:
            continue
    return False


# ============================================================
# Dashboard
# ============================================================

@staff_required
def dashboard_view(request):
    today = timezone.localdate()
    start = today - timedelta(days=29)

    summary = services.compute_revenue_summary(start, today)
    collections = services.compute_daily_collections(start, today)

    pending_payments = Payment.objects.filter(status=PaymentStatus.PROCESSING).select_related('invoice__booking')[:10]
    failed_payments = Payment.objects.filter(status=PaymentStatus.FAILED).select_related('invoice__booking').order_by('-created_at')[:10]
    recent_payments = Payment.objects.filter(status=PaymentStatus.COMPLETED).select_related('invoice__booking').order_by('-created_at')[:10]
    unpaid_invoices_count = Invoice.objects.filter(status__in=[InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID]).count()

    return render(request, 'payments/dashboard.html', {
        'summary': summary,
        'pending_payments': pending_payments,
        'failed_payments': failed_payments,
        'recent_payments': recent_payments,
        'unpaid_invoices_count': unpaid_invoices_count,
        'collections_labels': json.dumps([row['date'].strftime('%b %d') for row in collections]),
        'collections_cash': json.dumps([float(row['cash_total']) for row in collections]),
        'collections_mpesa': json.dumps([float(row['mpesa_total']) for row in collections]),
    })


# ============================================================
# Transactions (Payments)
# ============================================================

def _filtered_payments_queryset(request):
    queryset = Payment.objects.select_related('invoice__booking', 'initiated_by').all()
    form = TransactionSearchForm(request.GET)

    if form.is_valid():
        q = form.cleaned_data.get('q')
        if q:
            queryset = queryset.filter(
                Q(mpesa_receipt_number__icontains=q) | Q(invoice__booking__vehicle__license_plate__icontains=q)
                | Q(phone_number__icontains=q) | Q(invoice__booking__customer__first_name__icontains=q)
                | Q(invoice__booking__customer__last_name__icontains=q),
            )
        method = form.cleaned_data.get('method')
        if method:
            queryset = queryset.filter(method=method)
        status = form.cleaned_data.get('status')
        if status:
            queryset = queryset.filter(status=status)
        date_from = form.cleaned_data.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        date_to = form.cleaned_data.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

    return queryset.order_by('-created_at'), form


@staff_required
def payment_list_view(request):
    payments, form = _filtered_payments_queryset(request)
    paginator = Paginator(payments, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))

    querystring = request.GET.copy()
    querystring.pop('page', None)

    return render(request, 'payments/payment_list.html', {
        'search_form': form, 'page_obj': page_obj, 'querystring': querystring.urlencode(),
    })


@staff_required
def payment_detail_view(request, public_id):
    payment = get_object_or_404(
        Payment.objects.select_related('invoice__booking__customer', 'invoice__booking__service', 'initiated_by'),
        public_id=public_id,
    )
    refund_form = RefundForm()
    return render(request, 'payments/payment_detail.html', {'payment': payment, 'refund_form': refund_form})


@staff_required
@require_POST
def payment_verify_view(request, public_id):
    payment = get_object_or_404(Payment, public_id=public_id)
    try:
        services.verify_mpesa_payment(payment)
        payment.refresh_from_db()
        if payment.status == PaymentStatus.COMPLETED:
            messages.success(request, 'Payment confirmed as completed.')
        elif payment.status == PaymentStatus.FAILED:
            messages.warning(request, f'Daraja reports this payment failed: {payment.result_description}')
        else:
            messages.info(request, 'Still processing according to Daraja -- try again shortly.')
        _log(request, AuditLog.Action.UPDATE, 'Payment', payment, f'Verified {payment.reference_code} against Daraja')
    except (ValidationError, daraja.DarajaError) as exc:
        messages.error(request, str(exc))
    return redirect('payments:payment_detail', public_id=payment.public_id)


@management_required
@ratelimit(key='user', rate=settings.RATELIMIT_PAYMENT_ACTION, method='POST', block=True)
def payment_refund_view(request, public_id):
    payment = get_object_or_404(Payment, public_id=public_id)
    if request.method == 'POST':
        form = RefundForm(request.POST)
        if form.is_valid():
            try:
                refund = services.record_refund(payment, form.cleaned_data['amount'], form.cleaned_data['reason'], request.user)
                _log(request, AuditLog.Action.CREATE, 'Refund', refund, f'Refunded KSh {refund.amount} for {payment.reference_code}')
                messages.success(request, f'{refund.reference_code} recorded.')
                return redirect('payments:payment_detail', public_id=payment.public_id)
            except ValidationError as exc:
                messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
    else:
        form = RefundForm()
    return render(request, 'payments/payment_refund.html', {'form': form, 'payment': payment})


@staff_required
def payment_receipt_pdf_view(request, public_id):
    payment = get_object_or_404(Payment.objects.select_related('invoice__booking'), public_id=public_id)
    return payment_receipt_pdf_response(payment)


@staff_required
def payment_export_csv_view(request):
    payments, _ = _filtered_payments_queryset(request)
    return transactions_csv_response(payments)


@staff_required
def payment_export_excel_view(request):
    payments, _ = _filtered_payments_queryset(request)
    return transactions_excel_response(payments)


# ============================================================
# Invoices
# ============================================================

@staff_required
def invoice_list_view(request):
    invoices = Invoice.objects.select_related('booking__customer', 'booking__service').order_by('-created_at')
    status = request.GET.get('status')
    if status in InvoiceStatus.values:
        invoices = invoices.filter(status=status)

    paginator = Paginator(invoices, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'payments/invoice_list.html', {'page_obj': page_obj})


@staff_required
def invoice_detail_view(request, public_id):
    invoice = get_object_or_404(
        Invoice.objects.select_related('booking__customer', 'booking__service', 'booking__vehicle'), public_id=public_id,
    )
    payments = invoice.payments.order_by('-created_at')
    cash_form = CashPaymentForm(initial={'amount': invoice.balance})
    mpesa_form = MpesaPaymentForm(initial={'amount': invoice.balance, 'phone_number': invoice.booking.customer.phone_number})
    return render(request, 'payments/invoice_detail.html', {
        'invoice': invoice, 'payments': payments, 'cash_form': cash_form, 'mpesa_form': mpesa_form,
    })


@staff_required
def invoice_pdf_view(request, public_id):
    invoice = get_object_or_404(Invoice.objects.select_related('booking'), public_id=public_id)
    return invoice_pdf_response(invoice)


@management_required
@require_POST
def invoice_void_view(request, public_id):
    invoice = get_object_or_404(Invoice, public_id=public_id)
    try:
        services.void_invoice(invoice, request.user)
        _log(request, AuditLog.Action.UPDATE, 'Invoice', invoice, f'Voided {invoice.invoice_number}')
        messages.success(request, f'{invoice.invoice_number} has been voided.')
    except ValidationError as exc:
        messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
    return redirect('payments:invoice_detail', public_id=invoice.public_id)


@staff_required
@require_POST
def invoice_record_cash_view(request, public_id):
    invoice = get_object_or_404(Invoice, public_id=public_id)
    form = CashPaymentForm(request.POST)
    if form.is_valid():
        try:
            payment = services.record_cash_payment(invoice, form.cleaned_data['amount'], request.user, form.cleaned_data.get('notes', ''))
            _log(request, AuditLog.Action.CREATE, 'Payment', payment, f'Recorded cash payment {payment.reference_code} for {invoice.invoice_number}')
            messages.success(request, f'Cash payment of KSh {payment.amount:,.2f} recorded.')
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
    else:
        messages.error(request, 'Please correct the errors in the cash payment form.')
    return redirect('payments:invoice_detail', public_id=invoice.public_id)


@staff_required
@require_POST
@ratelimit(key='user', rate=settings.RATELIMIT_MPESA_INITIATE, block=True)
def invoice_initiate_mpesa_view(request, public_id):
    invoice = get_object_or_404(Invoice, public_id=public_id)
    form = MpesaPaymentForm(request.POST)
    if form.is_valid():
        try:
            payment = services.initiate_mpesa_payment(
                invoice, form.cleaned_data['phone_number'], form.cleaned_data['amount'], request.user,
            )
            _log(request, AuditLog.Action.CREATE, 'Payment', payment, f'Initiated M-Pesa STK push {payment.reference_code} for {invoice.invoice_number}')
            messages.success(request, 'STK push sent -- ask the customer to check their phone.')
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
    else:
        messages.error(request, 'Please correct the errors in the M-Pesa payment form.')
    return redirect('payments:invoice_detail', public_id=invoice.public_id)


# ============================================================
# Daily collections / revenue reports
# ============================================================

@staff_required
def collections_view(request):
    form = CollectionsRangeForm(request.GET or None)
    today = timezone.localdate()
    date_from = today - timedelta(days=29)
    date_to = today
    if form.is_valid():
        date_from = form.cleaned_data.get('date_from') or date_from
        date_to = form.cleaned_data.get('date_to') or date_to

    rows = services.compute_daily_collections(date_from, date_to)
    summary = services.compute_revenue_summary(date_from, date_to)

    return render(request, 'payments/collections.html', {
        'form': form, 'rows': rows, 'summary': summary, 'date_from': date_from, 'date_to': date_to,
    })


@staff_required
def collections_export_csv_view(request):
    form = CollectionsRangeForm(request.GET or None)
    today = timezone.localdate()
    date_from = today - timedelta(days=29)
    date_to = today
    if form.is_valid():
        date_from = form.cleaned_data.get('date_from') or date_from
        date_to = form.cleaned_data.get('date_to') or date_to
    rows = services.compute_daily_collections(date_from, date_to)
    return collections_csv_response(rows)


# ============================================================
# M-Pesa callback (Safaricom calls this directly -- no login, no CSRF)
# ============================================================

@csrf_exempt
@require_POST
@ratelimit(key='ip', rate=settings.RATELIMIT_MPESA_CALLBACK, block=True)
def mpesa_callback_view(request):
    caller_ip = _client_ip(request)
    if not _is_allowed_mpesa_ip(caller_ip):
        AuditLog.objects.create(
            action=AuditLog.Action.OTHER, description=f'Rejected M-Pesa callback from disallowed IP {caller_ip}',
            ip_address=caller_ip,
        )
        return HttpResponseForbidden('IP not allowed.')

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest('Invalid JSON payload.')

    services.process_mpesa_callback(payload)
    # Daraja expects this exact acknowledgement shape regardless of what
    # we did with the callback internally.
    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})


# ============================================================
# Customer self-service
# ============================================================

@customer_required
@ratelimit(key='user', rate=settings.RATELIMIT_MPESA_INITIATE, method='POST', block=True)
def my_pay_view(request, booking_public_id):
    customer = _get_own_customer_profile(request)
    if customer is None:
        return redirect('accounts:profile')

    from apps.bookings.models import Booking
    booking = get_object_or_404(Booking.objects.select_related('service'), public_id=booking_public_id, customer=customer)
    invoice = getattr(booking, 'invoice', None)
    if invoice is None:
        messages.error(request, 'This booking does not have an invoice yet -- it may not be confirmed.')
        return redirect('bookings:my_detail', public_id=booking.public_id)
    if invoice.status == InvoiceStatus.PAID:
        messages.info(request, 'This booking is already fully paid.')
        return redirect('bookings:my_detail', public_id=booking.public_id)

    if request.method == 'POST':
        form = MpesaPaymentForm(request.POST)
        if form.is_valid():
            try:
                payment = services.initiate_mpesa_payment(
                    invoice, form.cleaned_data['phone_number'], form.cleaned_data['amount'], request.user,
                )
                messages.success(request, 'Check your phone and enter your M-Pesa PIN to complete the payment.')
                return redirect('payments:my_payment_status', public_id=payment.public_id)
            except ValidationError as exc:
                messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
    else:
        form = MpesaPaymentForm(initial={'amount': invoice.balance, 'phone_number': customer.phone_number})

    return render(request, 'payments/my_pay.html', {'form': form, 'booking': booking, 'invoice': invoice})


@customer_required
def my_payment_status_view(request, public_id):
    customer = _get_own_customer_profile(request)
    if customer is None:
        return redirect('accounts:profile')
    payment = get_object_or_404(
        Payment.objects.select_related('invoice__booking'), public_id=public_id, invoice__booking__customer=customer,
    )
    return render(request, 'payments/my_payment_status.html', {'payment': payment})


@customer_required
@require_GET
@ratelimit(key='user', rate=settings.RATELIMIT_PAYMENT_POLL, block=True)
def my_payment_poll_view(request, public_id):
    customer = _get_own_customer_profile(request)
    if customer is None:
        return JsonResponse({'error': 'not found'}, status=404)
    payment = get_object_or_404(Payment, public_id=public_id, invoice__booking__customer=customer)
    return JsonResponse({
        'status': payment.status,
        'status_display': payment.get_status_display(),
        'result_description': payment.result_description,
    })
