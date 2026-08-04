from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit_logs.models import AuditLog
from apps.core.decorators import management_required, staff_required

from . import exports, services
from .forms import DateRangeForm, ExpenseCategoryForm, ExpenseForm
from .models import Expense, ExpenseCategory

MANAGEMENT_ROLES = ('super_admin', 'manager')


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log(request, action, model_name, obj, description):
    AuditLog.objects.create(
        user=request.user, action=action, model_name=model_name,
        object_id=str(obj.pk), description=description,
        ip_address=_client_ip(request),
    )


def _date_range(request):
    """Parses ?start=&end= from the query string, falling back to the
    last 30 days on missing/invalid input. Every report view and its
    matching export view call this so the two always agree."""
    form = DateRangeForm(request.GET)
    default_start, default_end = services.default_date_range(30)
    if form.is_valid() and form.cleaned_data.get('start') and form.cleaned_data.get('end'):
        return form.cleaned_data['start'], form.cleaned_data['end'], form
    return default_start, default_end, DateRangeForm(initial={'start': default_start, 'end': default_end})


def _export_format(request):
    fmt = request.GET.get('format', 'csv').lower()
    return fmt if fmt in ('csv', 'excel', 'pdf') else 'csv'


def _respond_export(fmt, filename, title, subtitle, headers, rows, summary_lines=None):
    if fmt == 'excel':
        return exports.excel_response(filename, title, headers, rows, summary_lines)
    if fmt == 'pdf':
        return exports.pdf_response(filename, title, subtitle, headers, rows, summary_lines)
    return exports.csv_response(filename, headers, rows, summary_lines)


# ============================================================
# Hub
# ============================================================

@staff_required
def hub_view(request):
    is_management = request.user.role in MANAGEMENT_ROLES
    return render(request, 'reports/hub.html', {'is_management': is_management})


# ============================================================
# Revenue
# ============================================================

@management_required
def revenue_report_view(request):
    start, end, form = _date_range(request)
    data = services.revenue_report(start, end)
    return render(request, 'reports/revenue.html', {'form': form, 'start': start, 'end': end, **data})


@management_required
def revenue_report_export_view(request):
    start, end, _ = _date_range(request)
    data = services.revenue_report(start, end)
    headers = ['Date', 'Cash (KSh)', 'M-Pesa (KSh)', 'Total (KSh)']
    rows = [[row['date'], row['cash_total'], row['mpesa_total'], row['total']] for row in data['daily']]
    summary = data['summary']
    summary_lines = [
        f'Gross revenue: KSh {summary["gross_revenue"]:,.2f}',
        f'Refunded: KSh {summary["refunded"]:,.2f}',
        f'Net revenue: KSh {summary["net_revenue"]:,.2f}',
        f'Transactions: {summary["transaction_count"]}',
    ]
    return _respond_export(
        _export_format(request), 'shinehub-revenue-report', 'Revenue Report', f'{start} to {end}',
        headers, rows, summary_lines,
    )


# ============================================================
# Expenses report (read-only view over the Expense ledger + Purchases)
# ============================================================

@management_required
def expenses_report_view(request):
    start, end, form = _date_range(request)
    data = services.expenses_report(start, end)
    return render(request, 'reports/expenses_report.html', {'form': form, 'start': start, 'end': end, **data})


@management_required
def expenses_report_export_view(request):
    start, end, _ = _date_range(request)
    data = services.expenses_report(start, end)
    headers = ['Date', 'Category', 'Description', 'Amount (KSh)']
    rows = [[e.expense_date, e.category.name, e.description, e.amount] for e in data['expenses']]
    summary_lines = [
        f'Manual expenses: KSh {data["manual_total"]:,.2f}',
        f'Inventory purchases: KSh {data["purchases_total"]:,.2f}',
        f'Grand total: KSh {data["grand_total"]:,.2f}',
    ]
    return _respond_export(
        _export_format(request), 'shinehub-expenses-report', 'Expenses Report', f'{start} to {end}',
        headers, rows, summary_lines,
    )


# ============================================================
# Profit summary
# ============================================================

@management_required
def profit_report_view(request):
    start, end, form = _date_range(request)
    data = services.profit_summary(start, end)
    return render(request, 'reports/profit.html', {'form': form, 'start': start, 'end': end, **data})


@management_required
def profit_report_export_view(request):
    start, end, _ = _date_range(request)
    data = services.profit_summary(start, end)
    headers = ['Metric', 'Amount (KSh)']
    rows = [
        ['Net Revenue', data['net_revenue']],
        ['Manual Expenses', data['manual_expenses']],
        ['Inventory Purchases', data['purchases_total']],
        ['Total Expenses', data['total_expenses']],
        ['Net Profit', data['net_profit']],
    ]
    return _respond_export(
        _export_format(request), 'shinehub-profit-summary', 'Profit Summary', f'{start} to {end}', headers, rows,
    )


# ============================================================
# Bookings
# ============================================================

@staff_required
def bookings_report_view(request):
    start, end, form = _date_range(request)
    data = services.bookings_report(start, end)
    return render(request, 'reports/bookings_report.html', {'form': form, 'start': start, 'end': end, **data})


@staff_required
def bookings_report_export_view(request):
    start, end, _ = _date_range(request)
    data = services.bookings_report(start, end)
    headers = ['Date', 'Bookings']
    rows = [[row['scheduled_date'], row['count']] for row in data['by_day']]
    summary_lines = [
        f'Total bookings: {data["total_bookings"]}',
        f'Completed: {data["completed_count"]}',
        f'Cancelled: {data["cancelled_count"]}',
        f'No-shows: {data["no_show_count"]}',
        f'Revenue from completed bookings: KSh {data["revenue_from_completed"]:,.2f}',
    ]
    return _respond_export(
        _export_format(request), 'shinehub-bookings-report', 'Bookings Report', f'{start} to {end}',
        headers, rows, summary_lines,
    )


# ============================================================
# Services
# ============================================================

@staff_required
def services_report_view(request):
    start, end, form = _date_range(request)
    data = services.services_report(start, end)
    return render(request, 'reports/services_report.html', {'form': form, 'start': start, 'end': end, **data})


@staff_required
def services_report_export_view(request):
    start, end, _ = _date_range(request)
    data = services.services_report(start, end)
    headers = ['Service', 'Category', 'Bookings', 'Completed', 'Revenue (KSh)']
    rows = [[r.name, r.category.name, r.booking_count, r.completed_count, r.revenue] for r in data['rows']]
    return _respond_export(
        _export_format(request), 'shinehub-services-report', 'Service Popularity Report', f'{start} to {end}', headers, rows,
    )


# ============================================================
# Customers
# ============================================================

@staff_required
def customers_report_view(request):
    start, end, form = _date_range(request)
    data = services.customers_report(start, end)
    return render(request, 'reports/customers_report.html', {'form': form, 'start': start, 'end': end, **data})


@staff_required
def customers_report_export_view(request):
    start, end, _ = _date_range(request)
    data = services.customers_report(start, end)
    headers = ['Customer', 'Bookings', 'Total Spend (KSh)']
    rows = [[f'{c.first_name} {c.last_name}', c.booking_count, c.total_spend] for c in data['top_customers']]
    summary_lines = [
        f'New customers in range: {data["new_customer_count"]}',
        f'Repeat customers: {data["repeat_customer_count"]}',
    ]
    return _respond_export(
        _export_format(request), 'shinehub-customers-report', 'Customer Report', f'{start} to {end}',
        headers, rows, summary_lines,
    )


# ============================================================
# Vehicles
# ============================================================

@staff_required
def vehicles_report_view(request):
    start, end, form = _date_range(request)
    data = services.vehicles_report(start, end)
    return render(request, 'reports/vehicles_report.html', {'form': form, 'start': start, 'end': end, **data})


@staff_required
def vehicles_report_export_view(request):
    start, end, _ = _date_range(request)
    data = services.vehicles_report(start, end)
    headers = ['Vehicle', 'Customer', 'Bookings in Range']
    rows = [
        [f'{v.make} {v.model} ({v.license_plate})', f'{v.customer.first_name} {v.customer.last_name}', v.booking_count]
        for v in data['most_serviced']
    ]
    return _respond_export(
        _export_format(request), 'shinehub-vehicles-report', 'Vehicle Report', f'{start} to {end}', headers, rows,
    )


# ============================================================
# Employees (productivity)
# ============================================================

@management_required
def employees_report_view(request):
    start, end, form = _date_range(request)
    data = services.employees_report(start, end)
    return render(request, 'reports/employees_report.html', {'form': form, 'start': start, 'end': end, **data})


@management_required
def employees_report_export_view(request):
    start, end, _ = _date_range(request)
    data = services.employees_report(start, end)
    headers = ['Employee', 'Position', 'Completed Bookings', 'Revenue Generated (KSh)']
    rows = [
        [row.user.get_full_name() or row.user.username, row.get_position_display(), row.completed_count, row.revenue_generated]
        for row in data['rows']
    ]
    return _respond_export(
        _export_format(request), 'shinehub-employee-productivity', 'Employee Productivity Report', f'{start} to {end}',
        headers, rows,
    )


# ============================================================
# Inventory
# ============================================================

@staff_required
def inventory_report_view(request):
    start, end, form = _date_range(request)
    data = services.inventory_summary_report(start, end)
    return render(request, 'reports/inventory_report.html', {'form': form, 'start': start, 'end': end, **data})


@staff_required
def inventory_report_export_view(request):
    start, end, _ = _date_range(request)
    data = services.inventory_summary_report(start, end)
    headers = ['Item', 'Unit', 'Total Used in Range']
    rows = [[row['item__name'], row['item__unit'], row['total_used']] for row in data['top_consumed']]
    summary_lines = [
        f'Active items: {data["total_items"]}',
        f'Low stock items: {data["low_stock_count"]}',
        f'Current valuation: KSh {data["valuation_total"]:,.2f}',
        f'Purchases in range: {data["purchases_count"]} orders, KSh {data["purchases_total"]:,.2f}',
    ]
    return _respond_export(
        _export_format(request), 'shinehub-inventory-report', 'Inventory Report', f'{start} to {end}',
        headers, rows, summary_lines,
    )


# ============================================================
# Suppliers
# ============================================================

@staff_required
def suppliers_report_view(request):
    start, end, form = _date_range(request)
    data = services.suppliers_report(start, end)
    return render(request, 'reports/suppliers_report.html', {'form': form, 'start': start, 'end': end, **data})


@staff_required
def suppliers_report_export_view(request):
    start, end, _ = _date_range(request)
    data = services.suppliers_report(start, end)
    headers = ['Supplier', 'Orders Received', 'Total Value (KSh)']
    rows = [[row['supplier'].name, row['order_count'], row['total_value']] for row in data['rows']]
    return _respond_export(
        _export_format(request), 'shinehub-suppliers-report', 'Supplier Report', f'{start} to {end}', headers, rows,
    )


# ============================================================
# Expense ledger (CRUD -- feeds the Expenses/Profit reports above)
# ============================================================

@management_required
def expense_list_view(request):
    from django.core.paginator import Paginator

    expenses = Expense.objects.select_related('category').order_by('-expense_date')
    paginator = Paginator(expenses, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'reports/expense_list.html', {'page_obj': page_obj})


@management_required
def expense_create_view(request):
    if not ExpenseCategory.objects.filter(is_active=True).exists():
        messages.error(request, 'Create an expense category first.')
        return redirect('reports:expense_category_create')

    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.recorded_by = request.user
            expense.save()
            _log(request, AuditLog.Action.CREATE, 'Expense', expense, f'Recorded expense "{expense.description}" (KSh {expense.amount})')
            messages.success(request, 'Expense recorded.')
            return redirect('reports:expense_list')
    else:
        form = ExpenseForm(initial={'expense_date': timezone.localdate()})
    return render(request, 'reports/expense_form.html', {'form': form, 'is_create': True})


@management_required
def expense_edit_view(request, public_id):
    expense = get_object_or_404(Expense, public_id=public_id)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            _log(request, AuditLog.Action.UPDATE, 'Expense', expense, f'Updated expense "{expense.description}"')
            messages.success(request, 'Expense updated.')
            return redirect('reports:expense_list')
    else:
        form = ExpenseForm(instance=expense)
    return render(request, 'reports/expense_form.html', {'form': form, 'is_create': False, 'expense': expense})


@management_required
@require_POST
def expense_set_status_view(request, public_id, new_status):
    expense = get_object_or_404(Expense, public_id=public_id)
    expense.is_active = new_status == 'active'
    expense.save(update_fields=['is_active'])
    _log(request, AuditLog.Action.UPDATE, 'Expense', expense, f'Status set to {new_status} for "{expense.description}"')
    messages.success(request, f'Expense marked as {"active" if expense.is_active else "voided"}.')
    return redirect('reports:expense_list')


@management_required
def expense_category_list_view(request):
    categories = ExpenseCategory.objects.order_by('name')
    return render(request, 'reports/expense_category_list.html', {'categories': categories})


@management_required
def expense_category_create_view(request):
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = request.user
            category.save()
            _log(request, AuditLog.Action.CREATE, 'ExpenseCategory', category, f'Created expense category "{category.name}"')
            messages.success(request, f'{category.name} has been added.')
            return redirect('reports:expense_category_list')
    else:
        form = ExpenseCategoryForm()
    return render(request, 'reports/expense_category_form.html', {'form': form})
