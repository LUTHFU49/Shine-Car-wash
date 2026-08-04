from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.bookings.models import Booking, BookingStatus
from apps.core.decorators import staff_required
from apps.customers.models import Customer
from apps.employees.models import Employee
from apps.inventory.models import InventoryItem
from apps.payments.models import Invoice, Payment, PaymentStatus
from apps.services.models import Service
from apps.vehicles.models import Vehicle

# Bookings actively at the wash bay right now, for the "In Queue Now" tile.
ACTIVE_QUEUE_STATUSES = [BookingStatus.IN_QUEUE, BookingStatus.IN_PROGRESS]

# How the Recent Activity feed renders each event type.
_ACTIVITY_STYLES = {
    'booking_new': {'icon': 'fa-calendar-check', 'color': 'blue'},
    'booking_done': {'icon': 'fa-check-circle', 'color': 'green'},
    'customer_new': {'icon': 'fa-user-plus', 'color': 'pink'},
    'low_stock': {'icon': 'fa-boxes-stacked', 'color': 'amber'},
}


def _pct_change(current, previous):
    """Percentage change vs. the prior period. None when there's nothing to compare against."""
    if not previous:
        return None
    return round(((current - previous) / previous) * 100)


def _recent_activity(limit=4):
    """
    Merge the last few bookings, new customers, and low-stock alerts into
    one timestamp-ordered feed. Pulled straight from live data -- no
    placeholder rows.
    """
    events = []

    recent_bookings = (
        Booking.objects.select_related('vehicle', 'service')
        .order_by('-created_at')[:limit]
    )
    for booking in recent_bookings:
        is_done = booking.status == BookingStatus.COMPLETED
        style = _ACTIVITY_STYLES['booking_done' if is_done else 'booking_new']
        events.append({
            **style,
            'title': f'{"Wash completed" if is_done else "New booking"} #{booking.booking_code}',
            'subtitle': f'{booking.vehicle.license_plate} — {booking.service.name}',
            'timestamp': booking.created_at,
        })

    recent_customers = Customer.objects.order_by('-created_at')[:limit]
    for customer in recent_customers:
        events.append({
            **_ACTIVITY_STYLES['customer_new'],
            'title': 'New customer registered',
            'subtitle': f'{customer.full_name} — {customer.phone_number}',
            'timestamp': customer.created_at,
        })

    low_stock_items = (
        InventoryItem.objects.filter(is_active=True, low_stock_alerted_at__isnull=False)
        .order_by('-low_stock_alerted_at')[:limit]
    )
    for item in low_stock_items:
        events.append({
            **_ACTIVITY_STYLES['low_stock'],
            'title': 'Low inventory alert',
            'subtitle': f'{item.name} — {item.available_stock} {item.get_unit_display()} remaining',
            'timestamp': item.low_stock_alerted_at,
        })

    events.sort(key=lambda e: e['timestamp'], reverse=True)
    return events[:limit]


@login_required
def home_view(request):
    """
    Single dashboard entry point for every role. Role-specific quick
    actions are branched here rather than using separate URLs per role,
    so the URL space stays stable as later phases add real widgets,
    charts, and KPIs (see the Analytics phase) to this same template.
    """
    role_quick_actions = {
        Role.SUPER_ADMIN: [
            {'label': 'Django Admin', 'icon': 'fa-user-shield', 'url': '/admin/'},
            {'label': 'Manage Customers', 'icon': 'fa-users', 'url': reverse('customers:list')},
            {'label': 'Manage Vehicles', 'icon': 'fa-car', 'url': reverse('vehicles:list')},
            {'label': 'Manage Services', 'icon': 'fa-spray-can-sparkles', 'url': reverse('services:list')},
            {'label': 'Manage Bookings', 'icon': 'fa-calendar-check', 'url': reverse('bookings:list')},
            {'label': 'Manage Employees', 'icon': 'fa-people-group', 'url': reverse('employees:list')},
        ],
        Role.MANAGER: [
            {'label': 'Manage Customers', 'icon': 'fa-users', 'url': reverse('customers:list')},
            {'label': 'Manage Vehicles', 'icon': 'fa-car', 'url': reverse('vehicles:list')},
            {'label': 'Manage Services', 'icon': 'fa-spray-can-sparkles', 'url': reverse('services:list')},
            {'label': "Today's Queue", 'icon': 'fa-list-check', 'url': reverse('bookings:queue')},
            {'label': 'Manage Employees', 'icon': 'fa-people-group', 'url': reverse('employees:list')},
        ],
        Role.CASHIER: [
            {'label': 'Manage Customers', 'icon': 'fa-users', 'url': reverse('customers:list')},
            {'label': 'Manage Vehicles', 'icon': 'fa-car', 'url': reverse('vehicles:list')},
            {'label': "Today's Queue", 'icon': 'fa-list-check', 'url': reverse('bookings:queue')},
            {'label': 'Process Payment', 'icon': 'fa-cash-register', 'url': reverse('payments:invoice_list')},
        ],
        Role.EMPLOYEE: [
            {'label': 'My Assignments', 'icon': 'fa-clipboard-list', 'url': reverse('employees:my_assignments')},
            {'label': 'My Profile & Schedule', 'icon': 'fa-id-badge', 'url': reverse('employees:my_profile')},
            {'label': 'My Attendance', 'icon': 'fa-calendar-check', 'url': reverse('employees:my_attendance')},
            {'label': 'My Performance', 'icon': 'fa-star', 'url': reverse('employees:my_performance')},
        ],
        Role.CUSTOMER: [
            {'label': 'Book a Wash', 'icon': 'fa-calendar-plus', 'url': reverse('bookings:my_create')},
            {'label': 'My Bookings', 'icon': 'fa-clock-rotate-left', 'url': reverse('bookings:my_list')},
            {'label': 'My Vehicles', 'icon': 'fa-car', 'url': reverse('vehicles:my_list')},
            {'label': 'Browse Services', 'icon': 'fa-spray-can-sparkles', 'url': reverse('services:catalog')},
        ],
    }

    context = {
        'quick_actions': role_quick_actions.get(request.user.role, []),
    }

    # Staff roles get the live KPI tiles + activity feed; customers see their
    # own quick actions only (a customer-facing "MY stats" widget belongs to
    # a future phase, not this one, so we don't fabricate one here).
    if request.user.role != Role.CUSTOMER:
        today = timezone.now().date()
        period_start = today - timedelta(days=30)
        prev_period_start = today - timedelta(days=60)

        total_bookings = Booking.objects.count()
        bookings_this_period = Booking.objects.filter(created_at__date__gte=period_start).count()
        bookings_prev_period = Booking.objects.filter(
            created_at__date__gte=prev_period_start, created_at__date__lt=period_start,
        ).count()

        completed_payments = Payment.objects.filter(status=PaymentStatus.COMPLETED)
        revenue_total = completed_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        revenue_this_period = completed_payments.filter(
            created_at__date__gte=period_start,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        revenue_prev_period = completed_payments.filter(
            created_at__date__gte=prev_period_start, created_at__date__lt=period_start,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        active_customers = Customer.objects.filter(is_active=True).count()
        customers_this_period = Customer.objects.filter(
            is_active=True, created_at__date__gte=period_start,
        ).count()
        customers_prev_period = Customer.objects.filter(
            is_active=True, created_at__date__gte=prev_period_start, created_at__date__lt=period_start,
        ).count()

        in_queue_now = Booking.objects.filter(status__in=ACTIVE_QUEUE_STATUSES).count()

        today_counts = dict(
            Booking.objects.filter(scheduled_date=today)
            .values_list('status')
            .annotate(total=Count('id'))
        )
        today_breakdown = [
            {'label': label, 'value': today_counts.get(value, 0), 'status': value}
            for value, label in BookingStatus.choices
            if today_counts.get(value, 0) > 0
        ]

        context.update({
            'show_kpis': True,
            'total_bookings': total_bookings,
            'bookings_delta': _pct_change(bookings_this_period, bookings_prev_period),
            'revenue_total': revenue_total,
            'revenue_delta': _pct_change(float(revenue_this_period), float(revenue_prev_period)),
            'active_customers': active_customers,
            'customers_delta': _pct_change(customers_this_period, customers_prev_period),
            'in_queue_now': in_queue_now,
            'recent_activity': _recent_activity(),
            'today_bookings_total': sum(today_counts.values()),
            'today_breakdown': today_breakdown,
        })

    return render(request, 'dashboard/home.html', context)


# Category order controls the order sections render in the search dropdown.
_SEARCH_MIN_QUERY_LEN = 2
_SEARCH_PER_CATEGORY_LIMIT = 5


@staff_required
def global_search_view(request):
    """
    JSON endpoint behind the topbar search overlay. Staff-only (matches
    the roles that can already see Customers/Vehicles/Bookings/Employees/
    Inventory/Services/Payments through their own list views) -- this
    just searches across all of them from one box instead of making
    someone guess which module a record lives in.
    """
    query = request.GET.get('q', '').strip()
    results = {
        'customers': [], 'vehicles': [], 'bookings': [],
        'employees': [], 'inventory': [], 'services': [], 'invoices': [],
    }

    if len(query) < _SEARCH_MIN_QUERY_LEN:
        return JsonResponse({'query': query, 'results': results, 'total': 0})

    limit = _SEARCH_PER_CATEGORY_LIMIT

    for customer in Customer.objects.filter(
        Q(first_name__icontains=query) | Q(last_name__icontains=query)
        | Q(phone_number__icontains=query) | Q(email__icontains=query)
    )[:limit]:
        results['customers'].append({
            'title': customer.full_name,
            'subtitle': f'{customer.customer_code} · {customer.phone_number}',
            'url': reverse('customers:detail', args=[customer.public_id]),
        })

    for vehicle in Vehicle.objects.filter(
        Q(license_plate__icontains=query) | Q(make__icontains=query) | Q(model__icontains=query)
    ).select_related('customer')[:limit]:
        results['vehicles'].append({
            'title': vehicle.license_plate,
            'subtitle': f'{vehicle.display_name} — {vehicle.customer.full_name}',
            'url': reverse('vehicles:detail', args=[vehicle.public_id]),
        })

    for booking in Booking.objects.filter(
        Q(vehicle__license_plate__icontains=query) | Q(service__name__icontains=query)
        | Q(customer__first_name__icontains=query) | Q(customer__last_name__icontains=query)
    ).select_related('vehicle', 'service', 'customer')[:limit]:
        results['bookings'].append({
            'title': f'#{booking.booking_code}',
            'subtitle': f'{booking.vehicle.license_plate} — {booking.service.name}',
            'url': reverse('bookings:detail', args=[booking.public_id]),
        })

    for employee in Employee.objects.filter(
        Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query)
        | Q(user__username__icontains=query)
    ).select_related('user')[:limit]:
        results['employees'].append({
            'title': employee.full_name,
            'subtitle': employee.get_position_display(),
            'url': reverse('employees:detail', args=[employee.public_id]),
        })

    for item in InventoryItem.objects.filter(
        Q(name__icontains=query) | Q(sku__icontains=query)
    )[:limit]:
        results['inventory'].append({
            'title': item.name,
            'subtitle': item.sku,
            'url': reverse('inventory:item_detail', args=[item.public_id]),
        })

    for service in Service.objects.filter(name__icontains=query)[:limit]:
        results['services'].append({
            'title': service.name,
            'subtitle': f'KSh {service.price}',
            'url': reverse('services:detail', args=[service.public_id]),
        })

    for invoice in Invoice.objects.filter(
        Q(booking__vehicle__license_plate__icontains=query)
        | Q(booking__customer__first_name__icontains=query)
        | Q(booking__customer__last_name__icontains=query)
    ).select_related('booking__vehicle', 'booking__customer')[:limit]:
        results['invoices'].append({
            'title': invoice.invoice_number,
            'subtitle': f'{invoice.booking.vehicle.license_plate} — KSh {invoice.total_amount}',
            'url': reverse('payments:invoice_detail', args=[invoice.public_id]),
        })

    total = sum(len(bucket) for bucket in results.values())
    return JsonResponse({'query': query, 'results': results, 'total': total})
