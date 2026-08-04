from apps.core.csv_utils import safe_csv_writer, safe_excel_row

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit_logs.models import AuditLog
from apps.core.decorators import management_required, staff_required

from .forms import ServiceCategoryForm, ServiceForm, ServiceSearchForm
from .models import Service, ServiceCategory, ServiceStatus

PAGE_SIZE = 20


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


# ============================================================
# Public catalog -- no login required
# ============================================================

def service_catalog_view(request):
    categories = (
        ServiceCategory.objects.filter(is_active=True)
        .prefetch_related('services')
        .order_by('display_order', 'name')
    )
    # Only active services within each active category; annotate so the
    # template doesn't need to filter a related manager itself.
    categorized = []
    for category in categories:
        active_services = [s for s in category.services.all() if s.status == ServiceStatus.ACTIVE]
        if active_services:
            categorized.append((category, active_services))

    return render(request, 'services/catalog.html', {'categorized': categorized})


# ============================================================
# Staff-facing: Service management
# ============================================================

def _staff_filtered_queryset(request):
    queryset = Service.objects.select_related('category').all()

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(description__icontains=q))

    category_id = request.GET.get('category', '')
    if category_id:
        queryset = queryset.filter(category_id=category_id)

    status = request.GET.get('status', '')
    if status in ServiceStatus.values:
        queryset = queryset.filter(status=status)

    sort = request.GET.get('sort', 'name')
    if sort in {'name', '-price', 'price', '-created_at'}:
        queryset = queryset.order_by(sort)

    return queryset.distinct()


@staff_required
def service_list_view(request):
    search_form = ServiceSearchForm(request.GET)
    queryset = _staff_filtered_queryset(request)

    paginator = Paginator(queryset, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))

    querystring = request.GET.copy()
    querystring.pop('page', None)

    return render(request, 'services/manage_list.html', {
        'search_form': search_form,
        'page_obj': page_obj,
        'total_count': queryset.count(),
        'querystring': querystring.urlencode(),
    })


@management_required
def service_create_view(request):
    if not ServiceCategory.objects.filter(is_active=True).exists():
        messages.error(request, 'Create a service category first.')
        return redirect('services:category_create')

    if request.method == 'POST':
        form = ServiceForm(request.POST, request.FILES)
        if form.is_valid():
            service = form.save(commit=False)
            service.created_by = request.user
            service.save()
            _log(request, AuditLog.Action.CREATE, 'Service', service, f'Created service "{service.name}" (KSh {service.price})')
            messages.success(request, f'{service.name} has been added to the catalog.')
            return redirect('services:detail', public_id=service.public_id)
    else:
        form = ServiceForm()

    return render(request, 'services/form.html', {'form': form, 'is_create': True})


@staff_required
def service_detail_view(request, public_id):
    service = get_object_or_404(Service.objects.select_related('category'), public_id=public_id)
    history = AuditLog.objects.filter(
        model_name='Service', object_id=str(service.pk),
    ).select_related('user').order_by('-created_at')[:50]
    return render(request, 'services/detail.html', {'service': service, 'history': history})


@management_required
def service_edit_view(request, public_id):
    service = get_object_or_404(Service, public_id=public_id)

    if request.method == 'POST':
        old_price = service.price
        form = ServiceForm(request.POST, request.FILES, instance=service)
        if form.is_valid():
            updated = form.save()
            price_note = f' (price changed from KSh {old_price} to KSh {updated.price})' if old_price != updated.price else ''
            _log(request, AuditLog.Action.UPDATE, 'Service', updated, f'Updated service "{updated.name}"{price_note}')
            messages.success(request, 'Service updated.')
            return redirect('services:detail', public_id=service.public_id)
    else:
        form = ServiceForm(instance=service)

    return render(request, 'services/form.html', {'form': form, 'is_create': False, 'service': service})


@management_required
@require_POST
def service_set_status_view(request, public_id, new_status):
    if new_status not in ServiceStatus.values:
        messages.error(request, 'Invalid status.')
        return redirect('services:list')

    service = get_object_or_404(Service, public_id=public_id)
    service.status = new_status
    service.save(update_fields=['status'])
    _log(request, AuditLog.Action.UPDATE, 'Service', service, f'Status changed to "{service.get_status_display()}" for "{service.name}"')
    messages.success(request, f'{service.name} marked as {service.get_status_display()}.')
    return redirect('services:detail', public_id=service.public_id)


@staff_required
def service_export_csv_view(request):
    queryset = _staff_filtered_queryset(request)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="shinehub-services.csv"'

    writer = safe_csv_writer(response)
    writer.writerow(['Name', 'Category', 'Price (KSh)', 'Duration (min)', 'Status', 'Available Days'])
    for service in queryset:
        writer.writerow([
            service.name, service.category.name, service.price, service.duration_minutes,
            service.get_status_display(), service.available_days_display,
        ])
    return response


@staff_required
def service_export_excel_view(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    queryset = _staff_filtered_queryset(request)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Services'

    headers = ['Name', 'Category', 'Price (KSh)', 'Duration (min)', 'Status', 'Available Days']
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for service in queryset:
        sheet.append(safe_excel_row([
            service.name, service.category.name, float(service.price), service.duration_minutes,
            service.get_status_display(), service.available_days_display,
        ]))

    for column_cells in sheet.columns:
        length = max((len(str(cell.value)) for cell in column_cells if cell.value is not None), default=10)
        sheet.column_dimensions[column_cells[0].column_letter].width = max(12, length + 2)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="shinehub-services.xlsx"'
    workbook.save(response)
    return response


# ============================================================
# Staff-facing: Service Category management
# ============================================================

@staff_required
def category_list_view(request):
    categories = ServiceCategory.objects.all().order_by('display_order', 'name')
    return render(request, 'services/category_list.html', {'categories': categories})


@management_required
def category_create_view(request):
    if request.method == 'POST':
        form = ServiceCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = request.user
            category.save()
            _log(request, AuditLog.Action.CREATE, 'ServiceCategory', category, f'Created service category "{category.name}"')
            messages.success(request, f'{category.name} category created.')
            return redirect('services:category_list')
    else:
        form = ServiceCategoryForm()

    return render(request, 'services/category_form.html', {'form': form, 'is_create': True})


@management_required
def category_edit_view(request, public_id):
    category = get_object_or_404(ServiceCategory, public_id=public_id)

    if request.method == 'POST':
        form = ServiceCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            _log(request, AuditLog.Action.UPDATE, 'ServiceCategory', category, f'Updated service category "{category.name}"')
            messages.success(request, 'Category updated.')
            return redirect('services:category_list')
    else:
        form = ServiceCategoryForm(instance=category)

    return render(request, 'services/category_form.html', {'form': form, 'is_create': False, 'category': category})


@management_required
@require_POST
def category_set_status_view(request, public_id, new_status):
    if new_status not in {'active', 'inactive'}:
        messages.error(request, 'Invalid status.')
        return redirect('services:category_list')

    category = get_object_or_404(ServiceCategory, public_id=public_id)
    category.is_active = (new_status == 'active')
    category.save(update_fields=['is_active'])
    _log(request, AuditLog.Action.UPDATE, 'ServiceCategory', category, f'{"Activated" if category.is_active else "Deactivated"} category "{category.name}"')
    messages.success(request, f'{category.name} {"activated" if category.is_active else "deactivated"}.')
    return redirect('services:category_list')
