import calendar
from apps.core.csv_utils import safe_csv_writer, safe_excel_row
from collections import defaultdict
from datetime import date, timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit_logs.models import AuditLog
from apps.core.decorators import customer_required, staff_required
from apps.customers.models import Customer
from apps.customers.selectors import search_active_customers

from .emails import (
    send_booking_cancelled_email,
    send_booking_confirmed_email,
    send_booking_received_email,
)
from .forms import BookingSearchForm, CancelBookingForm, CustomerBookingForm, RescheduleForm, StaffBookingForm
from .models import Booking, BookingStatus, BookingType

PAGE_SIZE = 20


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log(request, action, booking, description):
    AuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action, model_name='Booking', object_id=str(booking.pk),
        description=description, ip_address=_client_ip(request),
    )


def _apply_snapshot(booking):
    booking.price_at_booking = booking.service.price
    booking.duration_minutes_at_booking = booking.service.duration_minutes


# ============================================================
# Customer-facing self-service: "My Bookings"
# ============================================================

def _get_own_customer_profile(request):
    return Customer.objects.filter(user=request.user).first()


@customer_required
def my_bookings_list_view(request):
    customer = _get_own_customer_profile(request)
    if customer is None:
        messages.error(request, 'Complete your profile with a phone number before booking a wash.')
        return redirect('accounts:profile')

    tab = request.GET.get('tab', 'upcoming')
    bookings = customer.bookings.select_related('vehicle', 'service').all()
    if tab == 'past':
        bookings = bookings.filter(
            Q(status__in=[BookingStatus.COMPLETED, BookingStatus.NO_SHOW])
        ).order_by('-scheduled_date', '-scheduled_time')
    elif tab == 'cancelled':
        bookings = bookings.filter(status=BookingStatus.CANCELLED).order_by('-scheduled_date')
    else:
        tab = 'upcoming'
        bookings = bookings.exclude(
            status__in=[BookingStatus.COMPLETED, BookingStatus.CANCELLED, BookingStatus.NO_SHOW]
        ).order_by('scheduled_date', 'scheduled_time')

    return render(request, 'bookings/my_list.html', {'bookings': bookings, 'active_tab': tab})


@customer_required
def my_booking_create_view(request):
    customer = _get_own_customer_profile(request)
    if customer is None:
        messages.error(request, 'Complete your profile with a phone number before booking a wash.')
        return redirect('accounts:profile')

    if not customer.vehicles.filter(status='active').exists():
        messages.error(request, 'Add a vehicle before booking a wash.')
        return redirect('vehicles:my_create')

    if request.method == 'POST':
        form = CustomerBookingForm(request.POST, customer=customer)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.customer = customer
            booking.booking_type = BookingType.ONLINE
            booking.status = BookingStatus.PENDING
            _apply_snapshot(booking)
            booking.save()
            _log(request, AuditLog.Action.CREATE, booking, f'{customer.full_name} requested {booking.service.name} for {booking.scheduled_date}')
            send_booking_received_email(booking)
            messages.success(request, f'Your booking request ({booking.booking_code}) has been received and is awaiting approval.')
            return redirect('bookings:my_detail', public_id=booking.public_id)
    else:
        form = CustomerBookingForm(customer=customer)

    return render(request, 'bookings/my_form.html', {'form': form, 'is_create': True})


@customer_required
def my_booking_detail_view(request, public_id):
    customer = _get_own_customer_profile(request)
    if customer is None:
        return redirect('accounts:profile')
    booking = get_object_or_404(
        Booking.objects.select_related('vehicle', 'service'), public_id=public_id, customer=customer,
    )
    return render(request, 'bookings/my_detail.html', {'booking': booking})


@customer_required
def my_booking_reschedule_view(request, public_id):
    customer = _get_own_customer_profile(request)
    if customer is None:
        return redirect('accounts:profile')
    booking = get_object_or_404(Booking, public_id=public_id, customer=customer)

    if booking.status not in {BookingStatus.PENDING, BookingStatus.CONFIRMED}:
        messages.error(request, 'This booking can no longer be rescheduled.')
        return redirect('bookings:my_detail', public_id=booking.public_id)

    if request.method == 'POST':
        old_date, old_time = booking.scheduled_date, booking.scheduled_time
        form = RescheduleForm(request.POST, instance=booking)
        if form.is_valid():
            form.save()
            _log(request, AuditLog.Action.UPDATE, booking, f'Rescheduled from {old_date} {old_time} to {booking.scheduled_date} {booking.scheduled_time}')
            messages.success(request, 'Your booking has been rescheduled.')
            return redirect('bookings:my_detail', public_id=booking.public_id)
    else:
        form = RescheduleForm(instance=booking)

    return render(request, 'bookings/my_reschedule.html', {'form': form, 'booking': booking})


@customer_required
def my_booking_cancel_view(request, public_id):
    customer = _get_own_customer_profile(request)
    if customer is None:
        return redirect('accounts:profile')
    booking = get_object_or_404(Booking, public_id=public_id, customer=customer)

    if not booking.can_transition_to(BookingStatus.CANCELLED):
        messages.error(request, 'This booking can no longer be cancelled.')
        return redirect('bookings:my_detail', public_id=booking.public_id)

    if request.method == 'POST':
        form = CancelBookingForm(request.POST)
        if form.is_valid():
            booking.cancellation_reason = form.cleaned_data['reason']
            booking.cancelled_by = request.user
            booking.transition_to(BookingStatus.CANCELLED, extra_fields=['cancellation_reason', 'cancelled_by'])
            _log(request, AuditLog.Action.UPDATE, booking, f'{customer.full_name} cancelled their booking')
            send_booking_cancelled_email(booking)
            messages.success(request, 'Your booking has been cancelled.')
            return redirect('bookings:my_list')
    else:
        form = CancelBookingForm()

    return render(request, 'bookings/my_cancel.html', {'form': form, 'booking': booking})


# ============================================================
# Staff-facing
# ============================================================

def _staff_filtered_queryset(request):
    queryset = Booking.objects.select_related('customer', 'vehicle', 'service').all()

    q = request.GET.get('q', '').strip()
    if q:
        # Split on whitespace so a full "First Last" name search works --
        # each term must match somewhere (any field), all terms must match
        # (across fields), rather than requiring the literal whole string
        # to appear in a single field.
        combined = Q()
        for term in q.split():
            combined &= (
                Q(vehicle__license_plate__icontains=term)
                | Q(customer__first_name__icontains=term)
                | Q(customer__last_name__icontains=term)
                | Q(customer__phone_number__icontains=term)
                | Q(service__name__icontains=term)
            )
        queryset = queryset.filter(combined)

    status = request.GET.get('status', '')
    if status in BookingStatus.values:
        queryset = queryset.filter(status=status)

    date_from = request.GET.get('date_from', '')
    if date_from:
        queryset = queryset.filter(scheduled_date__gte=date_from)

    date_to = request.GET.get('date_to', '')
    if date_to:
        queryset = queryset.filter(scheduled_date__lte=date_to)

    return queryset.distinct().order_by('-scheduled_date', '-scheduled_time')


@staff_required
def booking_list_view(request):
    search_form = BookingSearchForm(request.GET)
    queryset = _staff_filtered_queryset(request)

    paginator = Paginator(queryset, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))

    querystring = request.GET.copy()
    querystring.pop('page', None)

    return render(request, 'bookings/list.html', {
        'search_form': search_form,
        'page_obj': page_obj,
        'total_count': queryset.count(),
        'querystring': querystring.urlencode(),
    })


@staff_required
def booking_create_view(request):
    preselected_customer = None
    customer_public_id = request.GET.get('customer') or request.POST.get('customer')
    if customer_public_id:
        preselected_customer = get_object_or_404(Customer, public_id=customer_public_id)

    if request.method == 'POST' and preselected_customer:
        form = StaffBookingForm(request.POST, customer=preselected_customer)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.customer = preselected_customer
            booking.booking_type = BookingType.WALK_IN
            booking.status = BookingStatus.CONFIRMED
            booking.created_by = request.user
            _apply_snapshot(booking)
            booking.save()
            booking.confirmation_email_sent_at = timezone.now()
            booking.save(update_fields=['confirmation_email_sent_at'])
            _log(request, AuditLog.Action.CREATE, booking, f'Walk-in booking created for {preselected_customer.full_name}: {booking.service.name}')
            send_booking_confirmed_email(booking)
            messages.success(request, f'Booking {booking.booking_code} created and confirmed.')
            return redirect('bookings:detail', public_id=booking.public_id)
    elif preselected_customer:
        form = StaffBookingForm(customer=preselected_customer)
    else:
        form = StaffBookingForm()
        if request.method == 'POST':
            messages.error(request, 'Select a customer for this booking.')

    customer_query = request.GET.get('customer_q', '').strip()
    customers = search_active_customers(customer_query) if not preselected_customer else []

    has_active_vehicle = preselected_customer and preselected_customer.vehicles.filter(status='active').exists()

    return render(request, 'bookings/form.html', {
        'form': form,
        'is_create': True,
        'preselected_customer': preselected_customer,
        'customers': customers,
        'customer_query': customer_query,
        'has_active_vehicle': has_active_vehicle,
    })


@staff_required
def booking_detail_view(request, public_id):
    booking = get_object_or_404(
        Booking.objects.select_related('customer', 'vehicle', 'service', 'assigned_employee__user'), public_id=public_id,
    )
    history = AuditLog.objects.filter(
        model_name='Booking', object_id=str(booking.pk),
    ).select_related('user').order_by('-created_at')[:50]

    from apps.employees.models import Employee, EmploymentStatus
    active_employees = Employee.objects.filter(employment_status=EmploymentStatus.ACTIVE).select_related('user')

    return render(request, 'bookings/detail.html', {'booking': booking, 'history': history, 'active_employees': active_employees})


@staff_required
def booking_reschedule_view(request, public_id):
    booking = get_object_or_404(Booking, public_id=public_id)

    if booking.status not in {BookingStatus.PENDING, BookingStatus.CONFIRMED}:
        messages.error(request, 'This booking can no longer be rescheduled.')
        return redirect('bookings:detail', public_id=booking.public_id)

    if request.method == 'POST':
        old_date, old_time = booking.scheduled_date, booking.scheduled_time
        form = RescheduleForm(request.POST, instance=booking)
        if form.is_valid():
            form.save()
            _log(request, AuditLog.Action.UPDATE, booking, f'Staff rescheduled from {old_date} {old_time} to {booking.scheduled_date} {booking.scheduled_time}')
            messages.success(request, 'Booking rescheduled.')
            return redirect('bookings:detail', public_id=booking.public_id)
    else:
        form = RescheduleForm(instance=booking)

    return render(request, 'bookings/reschedule.html', {'form': form, 'booking': booking})


@staff_required
def booking_cancel_view(request, public_id):
    booking = get_object_or_404(Booking, public_id=public_id)

    if not booking.can_transition_to(BookingStatus.CANCELLED):
        messages.error(request, 'This booking can no longer be cancelled.')
        return redirect('bookings:detail', public_id=booking.public_id)

    if request.method == 'POST':
        form = CancelBookingForm(request.POST)
        if form.is_valid():
            booking.cancellation_reason = form.cleaned_data['reason']
            booking.cancelled_by = request.user
            booking.transition_to(BookingStatus.CANCELLED, extra_fields=['cancellation_reason', 'cancelled_by'])
            _log(request, AuditLog.Action.UPDATE, booking, f'Staff cancelled booking{": " + form.cleaned_data["reason"] if form.cleaned_data["reason"] else ""}')
            send_booking_cancelled_email(booking)
            messages.success(request, f'{booking.booking_code} has been cancelled.')
            return redirect('bookings:detail', public_id=booking.public_id)
    else:
        form = CancelBookingForm()

    return render(request, 'bookings/cancel.html', {'form': form, 'booking': booking})


@staff_required
@require_POST
def booking_set_status_view(request, public_id, new_status):
    booking = get_object_or_404(Booking, public_id=public_id)

    if new_status not in BookingStatus.values or new_status == BookingStatus.CANCELLED:
        messages.error(request, 'Invalid status change.')
        return redirect('bookings:detail', public_id=booking.public_id)

    try:
        was_pending = booking.status == BookingStatus.PENDING
        booking.transition_to(new_status)
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
        return redirect('bookings:detail', public_id=booking.public_id)

    _log(request, AuditLog.Action.UPDATE, booking, f'Status changed to "{booking.get_status_display()}" for {booking.booking_code}')

    if new_status == BookingStatus.CONFIRMED and was_pending and not booking.confirmation_email_sent_at:
        send_booking_confirmed_email(booking)
        booking.confirmation_email_sent_at = timezone.now()
        booking.save(update_fields=['confirmation_email_sent_at'])

    messages.success(request, f'{booking.booking_code} marked as {booking.get_status_display()}.')
    return redirect('bookings:detail', public_id=booking.public_id)


@staff_required
@require_POST
def booking_assign_employee_view(request, public_id):
    booking = get_object_or_404(Booking, public_id=public_id)
    employee_public_id = request.POST.get('employee', '').strip()

    if not employee_public_id:
        booking.assigned_employee = None
        booking.save(update_fields=['assigned_employee'])
        _log(request, AuditLog.Action.UPDATE, booking, f'Unassigned employee from {booking.booking_code}')
        messages.success(request, 'Employee unassigned.')
        return redirect('bookings:detail', public_id=booking.public_id)

    from apps.employees.models import Employee
    employee = get_object_or_404(Employee, public_id=employee_public_id)
    booking.assigned_employee = employee
    booking.save(update_fields=['assigned_employee'])
    _log(request, AuditLog.Action.UPDATE, booking, f'{employee.full_name} assigned to {booking.booking_code}')
    messages.success(request, f'{employee.full_name} assigned to this booking.')
    return redirect('bookings:detail', public_id=booking.public_id)


@staff_required
def booking_calendar_view(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
        if not (1 <= month <= 12):
            raise ValueError
    except ValueError:
        year, month = today.year, today.month

    cal = calendar.Calendar(firstweekday=0)
    month_dates = cal.monthdatescalendar(year, month)

    counts = defaultdict(int)
    rows = (
        Booking.objects.filter(scheduled_date__year=year, scheduled_date__month=month)
        .exclude(status=BookingStatus.CANCELLED)
        .values('scheduled_date')
        .annotate(c=Count('id'))
    )
    for row in rows:
        counts[row['scheduled_date']] = row['c']

    first_day = date(year, month, 1)
    prev_last_day = first_day - timedelta(days=1)
    days_in_month = calendar.monthrange(year, month)[1]
    next_first_day = first_day + timedelta(days=days_in_month)

    return render(request, 'bookings/calendar.html', {
        'month_dates': month_dates,
        'year': year, 'month': month,
        'month_label': f'{calendar.month_name[month]} {year}',
        'counts': counts,
        'today': today,
        'prev_year': prev_last_day.year, 'prev_month': prev_last_day.month,
        'next_year': next_first_day.year, 'next_month': next_first_day.month,
    })


@staff_required
def booking_day_view(request, date_str):
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        raise Http404('Invalid date.')

    bookings = (
        Booking.objects.filter(scheduled_date=target_date)
        .exclude(status=BookingStatus.CANCELLED)
        .select_related('customer', 'vehicle', 'service', 'assigned_employee__user')
        .order_by('scheduled_time')
    )
    return render(request, 'bookings/day.html', {'bookings': bookings, 'target_date': target_date})


@staff_required
def booking_queue_view(request):
    today = timezone.localdate().isoformat()
    return redirect('bookings:day', date_str=today)


@staff_required
def booking_export_csv_view(request):
    queryset = _staff_filtered_queryset(request)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="shinehub-bookings.csv"'

    writer = safe_csv_writer(response)
    writer.writerow(['Booking Code', 'Customer', 'Vehicle', 'Service', 'Date', 'Time', 'Status', 'Price (KSh)', 'Type'])
    for booking in queryset:
        writer.writerow([
            booking.booking_code, booking.customer.full_name, booking.vehicle.license_plate, booking.service.name,
            booking.scheduled_date, booking.scheduled_time, booking.get_status_display(),
            booking.price_at_booking, booking.get_booking_type_display(),
        ])
    return response


@staff_required
def booking_export_excel_view(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    queryset = _staff_filtered_queryset(request)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Bookings'

    headers = ['Booking Code', 'Customer', 'Vehicle', 'Service', 'Date', 'Time', 'Status', 'Price (KSh)', 'Type']
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for booking in queryset:
        sheet.append(safe_excel_row([
            booking.booking_code, booking.customer.full_name, booking.vehicle.license_plate, booking.service.name,
            booking.scheduled_date.isoformat(), booking.scheduled_time.strftime('%H:%M'), booking.get_status_display(),
            float(booking.price_at_booking), booking.get_booking_type_display(),
        ]))

    for column_cells in sheet.columns:
        length = max((len(str(cell.value)) for cell in column_cells if cell.value is not None), default=10)
        sheet.column_dimensions[column_cells[0].column_letter].width = max(12, length + 2)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="shinehub-bookings.xlsx"'
    workbook.save(response)
    return response
