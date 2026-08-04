from apps.core.csv_utils import safe_csv_writer, safe_excel_row

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit_logs.models import AuditLog
from apps.core.decorators import staff_required

from .forms import CustomerForm, CustomerSearchForm
from .models import Customer

PAGE_SIZE = 20


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _filtered_queryset(request):
    """Shared between the list view and both export views so the exported
    file always matches exactly what's on screen."""
    queryset = Customer.objects.select_related('user', 'created_by').all()

    q = request.GET.get('q', '').strip()
    if q:
        text_matches = Q(first_name__icontains=q) | Q(last_name__icontains=q) \
            | Q(phone_number__icontains=q) | Q(email__icontains=q)

        code_pk = None
        if q.upper().startswith('CUST-'):
            digits = q.upper().replace('CUST-', '').lstrip('0')
            if digits.isdigit():
                code_pk = int(digits)

        if code_pk is not None:
            queryset = queryset.filter(text_matches | Q(pk=code_pk))
        else:
            queryset = queryset.filter(text_matches)

    status = request.GET.get('status', '')
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    source = request.GET.get('source', '')
    if source == 'linked':
        queryset = queryset.filter(user__isnull=False)
    elif source == 'walkin':
        queryset = queryset.filter(user__isnull=True)

    sort = request.GET.get('sort', '-created_at')
    if sort == 'name':
        queryset = queryset.order_by('last_name', 'first_name')
    elif sort == 'created_at':
        queryset = queryset.order_by('created_at')
    else:
        queryset = queryset.order_by('-created_at')

    return queryset.distinct()


@staff_required
def customer_list_view(request):
    search_form = CustomerSearchForm(request.GET)
    queryset = _filtered_queryset(request)

    paginator = Paginator(queryset, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))

    querystring = request.GET.copy()
    querystring.pop('page', None)

    return render(request, 'customers/list.html', {
        'search_form': search_form,
        'page_obj': page_obj,
        'total_count': queryset.count(),
        'querystring': querystring.urlencode(),
    })


@staff_required
def customer_create_view(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.created_by = request.user
            customer.save()
            AuditLog.objects.create(
                user=request.user, action=AuditLog.Action.CREATE, model_name='Customer',
                object_id=str(customer.pk), description=f'Registered walk-in customer {customer.full_name}',
                ip_address=_client_ip(request),
            )
            messages.success(request, f'{customer.full_name} has been added as a customer.')
            return redirect('customers:detail', public_id=customer.public_id)
    else:
        form = CustomerForm()

    return render(request, 'customers/form.html', {'form': form, 'is_create': True})


@staff_required
def customer_detail_view(request, public_id):
    customer = get_object_or_404(Customer, public_id=public_id)
    history = AuditLog.objects.filter(
        model_name='Customer', object_id=str(customer.pk),
    ).select_related('user').order_by('-created_at')[:50]

    return render(request, 'customers/detail.html', {
        'customer': customer,
        'history': history,
    })


@staff_required
def customer_edit_view(request, public_id):
    customer = get_object_or_404(Customer, public_id=public_id)

    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            AuditLog.objects.create(
                user=request.user, action=AuditLog.Action.UPDATE, model_name='Customer',
                object_id=str(customer.pk), description=f'Updated customer {customer.full_name}',
                ip_address=_client_ip(request),
            )
            messages.success(request, 'Customer record updated.')
            return redirect('customers:detail', public_id=customer.public_id)
    else:
        form = CustomerForm(instance=customer)

    return render(request, 'customers/form.html', {'form': form, 'is_create': False, 'customer': customer})


@staff_required
@require_POST
def customer_deactivate_view(request, public_id):
    customer = get_object_or_404(Customer, public_id=public_id)
    customer.is_active = False
    customer.deactivated_at = timezone.now()
    customer.save(update_fields=['is_active', 'deactivated_at'])
    AuditLog.objects.create(
        user=request.user, action=AuditLog.Action.UPDATE, model_name='Customer',
        object_id=str(customer.pk), description=f'Deactivated customer {customer.full_name}',
        ip_address=_client_ip(request),
    )
    messages.success(request, f'{customer.full_name} has been deactivated.')
    return redirect('customers:detail', public_id=customer.public_id)


@staff_required
@require_POST
def customer_reactivate_view(request, public_id):
    customer = get_object_or_404(Customer, public_id=public_id)
    customer.is_active = True
    customer.deactivated_at = None
    customer.save(update_fields=['is_active', 'deactivated_at'])
    AuditLog.objects.create(
        user=request.user, action=AuditLog.Action.UPDATE, model_name='Customer',
        object_id=str(customer.pk), description=f'Reactivated customer {customer.full_name}',
        ip_address=_client_ip(request),
    )
    messages.success(request, f'{customer.full_name} has been reactivated.')
    return redirect('customers:detail', public_id=customer.public_id)


@staff_required
def customer_export_csv_view(request):
    queryset = _filtered_queryset(request)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="shinehub-customers.csv"'

    writer = safe_csv_writer(response)
    writer.writerow(['Customer Code', 'First Name', 'Last Name', 'Email', 'Phone', 'Status', 'Source', 'Date Joined'])
    for customer in queryset:
        writer.writerow([
            customer.customer_code, customer.first_name, customer.last_name,
            customer.email, customer.phone_number,
            'Active' if customer.is_active else 'Deactivated',
            'Registered online' if customer.is_linked_account else 'Walk-in',
            customer.created_at.strftime('%Y-%m-%d %H:%M'),
        ])
    return response


@staff_required
def customer_export_excel_view(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    queryset = _filtered_queryset(request)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Customers'

    headers = ['Customer Code', 'First Name', 'Last Name', 'Email', 'Phone', 'Status', 'Source', 'Date Joined']
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for customer in queryset:
        sheet.append(safe_excel_row([
            customer.customer_code, customer.first_name, customer.last_name,
            customer.email, customer.phone_number,
            'Active' if customer.is_active else 'Deactivated',
            'Registered online' if customer.is_linked_account else 'Walk-in',
            customer.created_at.strftime('%Y-%m-%d %H:%M'),
        ]))

    for column_cells in sheet.columns:
        length = max((len(str(cell.value)) for cell in column_cells if cell.value is not None), default=10)
        sheet.column_dimensions[column_cells[0].column_letter].width = max(12, length + 2)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="shinehub-customers.xlsx"'
    workbook.save(response)
    return response
