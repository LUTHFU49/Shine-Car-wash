from apps.core.csv_utils import safe_csv_writer, safe_excel_row

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import Role
from apps.audit_logs.models import AuditLog
from apps.core.decorators import employee_required, management_required

from .emails import send_employee_welcome_email
from .forms import (
    AttendanceForm,
    EmployeeEditForm,
    EmployeeOnboardingForm,
    EmployeeSearchForm,
    PerformanceReviewForm,
)
from .models import Employee, EmploymentStatus

User = get_user_model()
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


# ============================================================
# Staff-facing (Super Admin / Manager only -- HR data is more sensitive
# than the pricing data Cashiers get read access to in the Services app)
# ============================================================

def _filtered_queryset(request):
    queryset = Employee.objects.select_related('user').all()

    q = request.GET.get('q', '').strip()
    if q:
        combined = Q()
        for term in q.split():
            combined &= (
                Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
                | Q(user__email__icontains=term)
                | Q(user__phone_number__icontains=term)
            )
        queryset = queryset.filter(combined)

    position = request.GET.get('position', '')
    if position:
        queryset = queryset.filter(position=position)

    status = request.GET.get('status', '')
    if status in EmploymentStatus.values:
        queryset = queryset.filter(employment_status=status)

    return queryset.distinct()


@management_required
def employee_list_view(request):
    search_form = EmployeeSearchForm(request.GET)
    queryset = _filtered_queryset(request)

    paginator = Paginator(queryset, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))

    querystring = request.GET.copy()
    querystring.pop('page', None)

    return render(request, 'employees/list.html', {
        'search_form': search_form,
        'page_obj': page_obj,
        'total_count': queryset.count(),
        'querystring': querystring.urlencode(),
    })


@management_required
def employee_create_view(request):
    if request.method == 'POST':
        form = EmployeeOnboardingForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            user = User.objects.create_user(
                username=data['username'], email=data['email'], password=None,
                first_name=data['first_name'], last_name=data['last_name'],
                phone_number=data['phone_number'], role=Role.EMPLOYEE,
            )
            employee = Employee.objects.create(
                user=user, position=data['position'], hire_date=data['hire_date'],
                scheduled_days=','.join(data.get('scheduled_days', [])),
                shift_start_time=data.get('shift_start_time'), shift_end_time=data.get('shift_end_time'),
                created_by=request.user,
            )

            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            set_password_path = reverse('accounts:password_reset_confirm', kwargs={'uidb64': uidb64, 'token': token})
            scheme = 'http' if settings.DEBUG else 'https'
            set_password_url = f'{scheme}://{settings.SITE_DOMAIN}{set_password_path}'
            send_employee_welcome_email(user, set_password_url)

            _log(request, AuditLog.Action.CREATE, 'Employee', employee, f'Onboarded employee {employee.full_name} as {employee.get_position_display()}')
            messages.success(request, f'{employee.full_name} has been added and emailed a link to set their password.')
            return redirect('employees:detail', public_id=employee.public_id)
    else:
        form = EmployeeOnboardingForm()

    return render(request, 'employees/form.html', {'form': form, 'is_create': True})


@management_required
def employee_detail_view(request, public_id):
    employee = get_object_or_404(Employee.objects.select_related('user'), public_id=public_id)
    attendance_records = employee.attendance_records.all()[:10]
    performance_reviews = employee.performance_reviews.select_related('reviewed_by').all()[:10]
    assigned_bookings = employee.assigned_bookings.select_related('customer', 'vehicle', 'service').exclude(
        status__in=['completed', 'cancelled', 'no_show'],
    ).order_by('scheduled_date', 'scheduled_time')[:10]
    history = AuditLog.objects.filter(
        model_name='Employee', object_id=str(employee.pk),
    ).select_related('user').order_by('-created_at')[:50]

    return render(request, 'employees/detail.html', {
        'employee': employee,
        'attendance_records': attendance_records,
        'performance_reviews': performance_reviews,
        'assigned_bookings': assigned_bookings,
        'history': history,
        'attendance_form': AttendanceForm(),
        'performance_form': PerformanceReviewForm(),
    })


@management_required
def employee_edit_view(request, public_id):
    employee = get_object_or_404(Employee, public_id=public_id)

    if request.method == 'POST':
        form = EmployeeEditForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            _log(request, AuditLog.Action.UPDATE, 'Employee', employee, f'Updated employee record for {employee.full_name}')
            messages.success(request, 'Employee record updated.')
            return redirect('employees:detail', public_id=employee.public_id)
    else:
        form = EmployeeEditForm(instance=employee)

    return render(request, 'employees/form.html', {'form': form, 'is_create': False, 'employee': employee})


@management_required
def attendance_create_view(request, public_id):
    employee = get_object_or_404(Employee, public_id=public_id)

    if request.method == 'POST':
        form = AttendanceForm(request.POST)
        if form.is_valid():
            record_date = form.cleaned_data['date']
            if employee.attendance_records.filter(date=record_date).exists():
                messages.error(request, f'An attendance record for {record_date} already exists for this employee.')
                return redirect('employees:detail', public_id=employee.public_id)

            record = form.save(commit=False)
            record.employee = employee
            record.recorded_by = request.user
            record.save()
            _log(request, AuditLog.Action.CREATE, 'Employee', employee, f'Recorded {record.get_status_display()} attendance for {employee.full_name} on {record.date}')
            messages.success(request, 'Attendance recorded.')
        else:
            messages.error(request, 'Could not save attendance record. Please check the form.')

    return redirect('employees:detail', public_id=employee.public_id)


@management_required
def performance_review_create_view(request, public_id):
    employee = get_object_or_404(Employee, public_id=public_id)

    if request.method == 'POST':
        form = PerformanceReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.employee = employee
            review.reviewed_by = request.user
            review.save()
            _log(request, AuditLog.Action.CREATE, 'Employee', employee, f'Added performance review ({review.rating}/5) for {employee.full_name}')
            messages.success(request, 'Performance review added.')
        else:
            messages.error(request, 'Could not save the review. Please check the form.')

    return redirect('employees:detail', public_id=employee.public_id)


@management_required
def employee_export_csv_view(request):
    queryset = _filtered_queryset(request)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="shinehub-employees.csv"'

    writer = safe_csv_writer(response)
    writer.writerow(['Employee Code', 'Name', 'Email', 'Phone', 'Position', 'Status', 'Hire Date', 'Schedule'])
    for employee in queryset:
        writer.writerow([
            employee.employee_code, employee.full_name, employee.user.email, employee.user.phone_number,
            employee.get_position_display(), employee.get_employment_status_display(),
            employee.hire_date, employee.scheduled_days_display,
        ])
    return response


@management_required
def employee_export_excel_view(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    queryset = _filtered_queryset(request)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Employees'

    headers = ['Employee Code', 'Name', 'Email', 'Phone', 'Position', 'Status', 'Hire Date', 'Schedule']
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for employee in queryset:
        sheet.append(safe_excel_row([
            employee.employee_code, employee.full_name, employee.user.email, employee.user.phone_number,
            employee.get_position_display(), employee.get_employment_status_display(),
            employee.hire_date.isoformat(), employee.scheduled_days_display,
        ]))

    for column_cells in sheet.columns:
        length = max((len(str(cell.value)) for cell in column_cells if cell.value is not None), default=10)
        sheet.column_dimensions[column_cells[0].column_letter].width = max(12, length + 2)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="shinehub-employees.xlsx"'
    workbook.save(response)
    return response


# ============================================================
# Employee self-service (read-only)
# ============================================================

def _get_own_employee_profile(request):
    return Employee.objects.filter(user=request.user).first()


@employee_required
def my_profile_view(request):
    employee = _get_own_employee_profile(request)
    if employee is None:
        messages.error(request, 'Your employee profile has not been set up yet. Contact your manager.')
        return redirect('dashboard:home')
    return render(request, 'employees/my_profile.html', {'employee': employee})


@employee_required
def my_attendance_view(request):
    employee = _get_own_employee_profile(request)
    if employee is None:
        messages.error(request, 'Your employee profile has not been set up yet. Contact your manager.')
        return redirect('dashboard:home')
    attendance_records = employee.attendance_records.all()[:30]
    return render(request, 'employees/my_attendance.html', {'employee': employee, 'attendance_records': attendance_records})


@employee_required
def my_performance_view(request):
    employee = _get_own_employee_profile(request)
    if employee is None:
        messages.error(request, 'Your employee profile has not been set up yet. Contact your manager.')
        return redirect('dashboard:home')
    performance_reviews = employee.performance_reviews.select_related('reviewed_by').all()
    return render(request, 'employees/my_performance.html', {'employee': employee, 'performance_reviews': performance_reviews})


@employee_required
def my_assignments_view(request):
    employee = _get_own_employee_profile(request)
    if employee is None:
        messages.error(request, 'Your employee profile has not been set up yet. Contact your manager.')
        return redirect('dashboard:home')
    assignments = employee.assigned_bookings.select_related('customer', 'vehicle', 'service').exclude(
        status__in=['completed', 'cancelled', 'no_show'],
    ).order_by('scheduled_date', 'scheduled_time')
    return render(request, 'employees/my_assignments.html', {'employee': employee, 'assignments': assignments})
