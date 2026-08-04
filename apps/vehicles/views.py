from apps.core.csv_utils import safe_csv_writer, safe_excel_row

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit_logs.models import AuditLog
from apps.core.decorators import customer_required, staff_required
from apps.customers.models import Customer

from .forms import CustomerVehicleForm, VehicleForm, VehicleSearchForm
from .models import Vehicle, VehicleStatus

PAGE_SIZE = 20


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log(request, action, vehicle, description):
    AuditLog.objects.create(
        user=request.user, action=action, model_name='Vehicle',
        object_id=str(vehicle.pk), description=description,
        ip_address=_client_ip(request),
    )


# ============================================================
# Staff-facing: manage vehicles for any customer
# ============================================================

def _staff_filtered_queryset(request):
    queryset = Vehicle.objects.select_related('customer', 'created_by').all()

    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(license_plate__icontains=q)
            | Q(make__icontains=q)
            | Q(model__icontains=q)
            | Q(customer__first_name__icontains=q)
            | Q(customer__last_name__icontains=q)
            | Q(customer__phone_number__icontains=q)
        )

    status = request.GET.get('status', '')
    if status in VehicleStatus.values:
        queryset = queryset.filter(status=status)

    vehicle_type = request.GET.get('vehicle_type', '')
    if vehicle_type:
        queryset = queryset.filter(vehicle_type=vehicle_type)

    sort = request.GET.get('sort', '-created_at')
    if sort == 'license_plate':
        queryset = queryset.order_by('license_plate')
    elif sort == 'created_at':
        queryset = queryset.order_by('created_at')
    else:
        queryset = queryset.order_by('-created_at')

    return queryset.distinct()


@staff_required
def vehicle_list_view(request):
    search_form = VehicleSearchForm(request.GET)
    queryset = _staff_filtered_queryset(request)

    paginator = Paginator(queryset, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))

    querystring = request.GET.copy()
    querystring.pop('page', None)

    return render(request, 'vehicles/list.html', {
        'search_form': search_form,
        'page_obj': page_obj,
        'total_count': queryset.count(),
        'querystring': querystring.urlencode(),
    })


@staff_required
def vehicle_create_view(request):
    preselected_customer = None
    customer_public_id = request.GET.get('customer') or request.POST.get('customer')
    if customer_public_id:
        preselected_customer = get_object_or_404(Customer, public_id=customer_public_id)

    if request.method == 'POST':
        form = VehicleForm(request.POST, request.FILES)
        if form.is_valid() and preselected_customer:
            vehicle = form.save(commit=False)
            vehicle.customer = preselected_customer
            vehicle.created_by = request.user
            vehicle.save()
            _log(request, AuditLog.Action.CREATE, vehicle, f'Registered vehicle {vehicle.license_plate} for {preselected_customer.full_name}')
            messages.success(request, f'{vehicle.display_name} ({vehicle.license_plate}) has been registered.')
            return redirect('vehicles:detail', public_id=vehicle.public_id)
        elif not preselected_customer:
            messages.error(request, 'Select a customer to register this vehicle under.')
    else:
        form = VehicleForm()

    # Staff pick a customer via search-as-you-type; simplest robust
    # implementation without a JS dependency is a plain searchable list.
    customer_query = request.GET.get('customer_q', '').strip()
    from apps.customers.selectors import search_active_customers
    customers = search_active_customers(customer_query)

    return render(request, 'vehicles/form.html', {
        'form': form,
        'is_create': True,
        'preselected_customer': preselected_customer,
        'customers': customers,
        'customer_query': customer_query,
    })


@staff_required
def vehicle_detail_view(request, public_id):
    vehicle = get_object_or_404(Vehicle.objects.select_related('customer'), public_id=public_id)
    history = AuditLog.objects.filter(
        model_name='Vehicle', object_id=str(vehicle.pk),
    ).select_related('user').order_by('-created_at')[:50]

    return render(request, 'vehicles/detail.html', {'vehicle': vehicle, 'history': history})


@staff_required
def vehicle_edit_view(request, public_id):
    vehicle = get_object_or_404(Vehicle, public_id=public_id)

    if request.method == 'POST':
        form = VehicleForm(request.POST, request.FILES, instance=vehicle)
        if form.is_valid():
            form.save()
            _log(request, AuditLog.Action.UPDATE, vehicle, f'Updated vehicle {vehicle.license_plate}')
            messages.success(request, 'Vehicle record updated.')
            return redirect('vehicles:detail', public_id=vehicle.public_id)
    else:
        form = VehicleForm(instance=vehicle)

    return render(request, 'vehicles/form.html', {'form': form, 'is_create': False, 'vehicle': vehicle})


@staff_required
@require_POST
def vehicle_set_status_view(request, public_id, new_status):
    if new_status not in VehicleStatus.values:
        messages.error(request, 'Invalid status.')
        return redirect('vehicles:list')

    vehicle = get_object_or_404(Vehicle, public_id=public_id)
    vehicle.status = new_status
    vehicle.save(update_fields=['status'])
    _log(request, AuditLog.Action.UPDATE, vehicle, f'Status changed to "{vehicle.get_status_display()}" for {vehicle.license_plate}')
    messages.success(request, f'{vehicle.license_plate} marked as {vehicle.get_status_display()}.')
    return redirect('vehicles:detail', public_id=vehicle.public_id)


@staff_required
def vehicle_export_csv_view(request):
    queryset = _staff_filtered_queryset(request)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="shinehub-vehicles.csv"'

    writer = safe_csv_writer(response)
    writer.writerow(['License Plate', 'Make', 'Model', 'Year', 'Color', 'Type', 'Status', 'Customer', 'Registered'])
    for vehicle in queryset:
        writer.writerow([
            vehicle.license_plate, vehicle.make, vehicle.model, vehicle.year, vehicle.color,
            vehicle.get_vehicle_type_display(), vehicle.get_status_display(),
            vehicle.customer.full_name, vehicle.created_at.strftime('%Y-%m-%d %H:%M'),
        ])
    return response


@staff_required
def vehicle_export_excel_view(request):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    queryset = _staff_filtered_queryset(request)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Vehicles'

    headers = ['License Plate', 'Make', 'Model', 'Year', 'Color', 'Type', 'Status', 'Customer', 'Registered']
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for vehicle in queryset:
        sheet.append(safe_excel_row([
            vehicle.license_plate, vehicle.make, vehicle.model, vehicle.year, vehicle.color,
            vehicle.get_vehicle_type_display(), vehicle.get_status_display(),
            vehicle.customer.full_name, vehicle.created_at.strftime('%Y-%m-%d %H:%M'),
        ]))

    for column_cells in sheet.columns:
        length = max((len(str(cell.value)) for cell in column_cells if cell.value is not None), default=10)
        sheet.column_dimensions[column_cells[0].column_letter].width = max(12, length + 2)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="shinehub-vehicles.xlsx"'
    workbook.save(response)
    return response


# ============================================================
# Customer-facing self-service: "My Vehicles"
# ============================================================

def _get_own_customer_profile(request):
    """
    Returns the logged-in customer's linked Customer profile, or None if
    one doesn't exist yet (e.g. an account created without a phone number).
    Every self-service vehicle view uses this instead of assuming the
    OneToOne reverse accessor always resolves.
    """
    return Customer.objects.filter(user=request.user).first()


@customer_required
def my_vehicles_list_view(request):
    customer = _get_own_customer_profile(request)
    if customer is None:
        messages.error(request, 'Complete your profile with a phone number before adding vehicles.')
        return redirect('accounts:profile')

    vehicles = customer.vehicles.all().order_by('-created_at')
    return render(request, 'vehicles/my_list.html', {'vehicles': vehicles, 'customer': customer})


@customer_required
def my_vehicle_create_view(request):
    customer = _get_own_customer_profile(request)
    if customer is None:
        messages.error(request, 'Complete your profile with a phone number before adding vehicles.')
        return redirect('accounts:profile')

    if request.method == 'POST':
        form = CustomerVehicleForm(request.POST, request.FILES)
        if form.is_valid():
            vehicle = form.save(commit=False)
            vehicle.customer = customer
            vehicle.save()
            _log(request, AuditLog.Action.CREATE, vehicle, f'Self-registered vehicle {vehicle.license_plate}')
            messages.success(request, f'{vehicle.display_name} has been added to your vehicles.')
            return redirect('vehicles:my_list')
    else:
        form = CustomerVehicleForm()

    return render(request, 'vehicles/my_form.html', {'form': form, 'is_create': True})


@customer_required
def my_vehicle_edit_view(request, public_id):
    customer = _get_own_customer_profile(request)
    if customer is None:
        messages.error(request, 'Complete your profile with a phone number first.')
        return redirect('accounts:profile')

    vehicle = get_object_or_404(Vehicle, public_id=public_id, customer=customer)

    if request.method == 'POST':
        form = CustomerVehicleForm(request.POST, request.FILES, instance=vehicle)
        if form.is_valid():
            form.save()
            _log(request, AuditLog.Action.UPDATE, vehicle, f'Customer updated vehicle {vehicle.license_plate}')
            messages.success(request, 'Vehicle updated.')
            return redirect('vehicles:my_list')
    else:
        form = CustomerVehicleForm(instance=vehicle)

    return render(request, 'vehicles/my_form.html', {'form': form, 'is_create': False, 'vehicle': vehicle})


@customer_required
@require_POST
def my_vehicle_mark_sold_view(request, public_id):
    customer = _get_own_customer_profile(request)
    if customer is None:
        return redirect('accounts:profile')

    vehicle = get_object_or_404(Vehicle, public_id=public_id, customer=customer)
    vehicle.status = VehicleStatus.SOLD
    vehicle.save(update_fields=['status'])
    _log(request, AuditLog.Action.UPDATE, vehicle, f'Customer marked vehicle {vehicle.license_plate} as sold')
    messages.success(request, f'{vehicle.license_plate} has been marked as sold and moved out of your active vehicles.')
    return redirect('vehicles:my_list')
