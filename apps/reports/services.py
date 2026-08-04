"""
One function per report. Every date-scoped function takes
(start_date, end_date) -- inclusive localdate() bounds -- and returns a
plain dict the view hands straight to the template and to
apps.reports.exports for CSV/Excel/PDF. Nothing here writes to the
database; this module is read-only aggregation over models owned by
other apps (bookings, services, customers, vehicles, employees,
inventory, payments) plus this app's own Expense ledger.
"""
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import ExtractHour, ExtractWeekDay, TruncDate
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.customers.models import Customer
from apps.employees.models import Employee
from apps.inventory.models import InventoryItem, Purchase, PurchaseStatus, StockMovement, Supplier
from apps.services.models import Service
from apps.vehicles.models import Vehicle

from .models import Expense

WEEKDAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']


def default_date_range(days=30):
    end = timezone.localdate()
    start = end - timezone.timedelta(days=days - 1)
    return start, end


# ============================================================
# Revenue (wraps apps.payments -- the ledger of truth for money in)
# ============================================================

def revenue_report(start_date, end_date):
    from apps.payments import services as payment_services

    summary = payment_services.compute_revenue_summary(start_date, end_date)
    daily = payment_services.compute_daily_collections(start_date, end_date)
    return {'summary': summary, 'daily': daily}


# ============================================================
# Expenses (manual Expense ledger + inventory Purchases as spend)
# ============================================================

def expenses_report(start_date, end_date):
    expenses = Expense.objects.filter(is_active=True, expense_date__range=[start_date, end_date])
    by_category = (
        expenses.values('category__name').annotate(total=Sum('amount')).order_by('-total')
    )
    manual_total = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    purchases = Purchase.objects.filter(status=PurchaseStatus.RECEIVED, received_date__range=[start_date, end_date])
    purchases_total = sum((p.total_amount for p in purchases), start=Decimal('0.00'))

    return {
        'expenses': expenses.select_related('category').order_by('-expense_date'),
        'by_category': list(by_category),
        'manual_total': manual_total,
        'purchases_total': purchases_total,
        'grand_total': manual_total + purchases_total,
    }


# ============================================================
# Profit summary (revenue vs. everything spent)
# ============================================================

def profit_summary(start_date, end_date):
    revenue = revenue_report(start_date, end_date)
    expenses = expenses_report(start_date, end_date)
    net_revenue = revenue['summary']['net_revenue']
    total_expenses = expenses['grand_total']
    return {
        'net_revenue': net_revenue,
        'total_expenses': total_expenses,
        'manual_expenses': expenses['manual_total'],
        'purchases_total': expenses['purchases_total'],
        'net_profit': net_revenue - total_expenses,
    }


# ============================================================
# Bookings (volume, status/type mix, peak hours & days)
# ============================================================

def bookings_report(start_date, end_date):
    bookings = Booking.objects.filter(scheduled_date__range=[start_date, end_date])

    by_status = list(bookings.values('status').annotate(count=Count('id')).order_by('-count'))
    by_type = list(bookings.values('booking_type').annotate(count=Count('id')).order_by('-count'))

    by_day = list(
        bookings.values('scheduled_date').annotate(count=Count('id')).order_by('scheduled_date')
    )

    by_hour_rows = (
        bookings.annotate(hour=ExtractHour('scheduled_time')).values('hour').annotate(count=Count('id')).order_by('hour')
    )
    hour_counts = {row['hour']: row['count'] for row in by_hour_rows}
    by_hour = [{'hour': h, 'count': hour_counts.get(h, 0)} for h in range(24)]

    by_weekday_rows = (
        bookings.annotate(weekday=ExtractWeekDay('scheduled_date')).values('weekday').annotate(count=Count('id'))
    )
    weekday_counts = {row['weekday']: row['count'] for row in by_weekday_rows}
    # Django's ExtractWeekDay is 1=Sunday..7=Saturday, matching WEEKDAY_NAMES order.
    by_weekday = [{'day': WEEKDAY_NAMES[i], 'count': weekday_counts.get(i + 1, 0)} for i in range(7)]

    completed = bookings.filter(status=BookingStatus.COMPLETED)
    revenue = completed.aggregate(total=Sum('price_at_booking'))['total'] or Decimal('0.00')

    return {
        'total_bookings': bookings.count(),
        'completed_count': completed.count(),
        'cancelled_count': bookings.filter(status=BookingStatus.CANCELLED).count(),
        'no_show_count': bookings.filter(status=BookingStatus.NO_SHOW).count(),
        'revenue_from_completed': revenue,
        'by_status': by_status,
        'by_type': by_type,
        'by_day': by_day,
        'by_hour': by_hour,
        'by_weekday': by_weekday,
    }


# ============================================================
# Services (popularity + revenue per service)
# ============================================================

def services_report(start_date, end_date):
    bookings = Booking.objects.filter(scheduled_date__range=[start_date, end_date])

    rows = (
        Service.objects.annotate(
            booking_count=Count('bookings', filter=Q(bookings__in=bookings)),
            completed_count=Count('bookings', filter=Q(bookings__in=bookings, bookings__status=BookingStatus.COMPLETED)),
            revenue=Sum('bookings__price_at_booking', filter=Q(bookings__in=bookings, bookings__status=BookingStatus.COMPLETED)),
        )
        .filter(booking_count__gt=0)
        .select_related('category')
        .order_by('-revenue')
    )

    for row in rows:
        row.revenue = row.revenue or Decimal('0.00')

    return {'rows': list(rows)}


# ============================================================
# Customers (growth, repeat customers, top spenders)
# ============================================================

def customers_report(start_date, end_date):
    new_customers = Customer.objects.filter(created_at__date__range=[start_date, end_date])
    by_day = list(
        new_customers.annotate(day=TruncDate('created_at')).values('day').annotate(count=Count('id')).order_by('day')
    )

    completed_bookings = Booking.objects.filter(status=BookingStatus.COMPLETED, scheduled_date__range=[start_date, end_date])
    top_customers = (
        Customer.objects.annotate(
            booking_count=Count('bookings', filter=Q(bookings__in=completed_bookings)),
            total_spend=Sum('bookings__price_at_booking', filter=Q(bookings__in=completed_bookings)),
        )
        .filter(booking_count__gt=0)
        .order_by('-total_spend')[:20]
    )
    for customer in top_customers:
        customer.total_spend = customer.total_spend or Decimal('0.00')

    repeat_customers = [c for c in top_customers if c.booking_count >= 2]

    return {
        'new_customer_count': new_customers.count(),
        'by_day': by_day,
        'top_customers': list(top_customers),
        'repeat_customers': repeat_customers,
        'repeat_customer_count': len(repeat_customers),
    }


# ============================================================
# Vehicles (fleet composition seen through bookings)
# ============================================================

def vehicles_report(start_date, end_date):
    by_type = list(Vehicle.objects.values('vehicle_type').annotate(count=Count('id')).order_by('-count'))

    bookings = Booking.objects.filter(scheduled_date__range=[start_date, end_date])
    most_serviced = (
        Vehicle.objects.annotate(booking_count=Count('bookings', filter=Q(bookings__in=bookings)))
        .filter(booking_count__gt=0)
        .select_related('customer')
        .order_by('-booking_count')[:20]
    )

    return {
        'total_vehicles': Vehicle.objects.count(),
        'by_type': by_type,
        'most_serviced': list(most_serviced),
    }


# ============================================================
# Employees (productivity -- management-only report)
# ============================================================

def employees_report(start_date, end_date):
    completed = Booking.objects.filter(
        status=BookingStatus.COMPLETED, scheduled_date__range=[start_date, end_date], assigned_employee__isnull=False,
    )

    rows = (
        Employee.objects.annotate(
            completed_count=Count('assigned_bookings', filter=Q(assigned_bookings__in=completed)),
            revenue_generated=Sum('assigned_bookings__price_at_booking', filter=Q(assigned_bookings__in=completed)),
        )
        .filter(completed_count__gt=0)
        .select_related('user')
        .order_by('-completed_count')
    )
    for row in rows:
        row.revenue_generated = row.revenue_generated or Decimal('0.00')

    by_position = list(
        Employee.objects.filter(employment_status='active').values('position').annotate(count=Count('id')).order_by('-count')
    )

    return {'rows': list(rows), 'by_position': by_position}


# ============================================================
# Inventory (current-state snapshot + movement in range)
# ============================================================

def inventory_summary_report(start_date, end_date):
    from apps.inventory import services as inventory_services

    items = InventoryItem.objects.filter(is_active=True).select_related('category')
    low_stock = [item for item in items if item.is_low_stock]

    consumed_rows = (
        StockMovement.objects.filter(
            movement_type=StockMovement.MovementType.BOOKING_USED, created_at__date__range=[start_date, end_date],
        )
        .values('item__name', 'item__unit')
        .annotate(total_used=Sum('quantity'))
        .order_by('-total_used')[:15]
    )

    purchases_in_range = Purchase.objects.filter(status=PurchaseStatus.RECEIVED, received_date__range=[start_date, end_date])
    purchases_total = sum((p.total_amount for p in purchases_in_range), start=Decimal('0.00'))

    return {
        'total_items': items.count(),
        'low_stock_count': len(low_stock),
        'low_stock_items': low_stock,
        'valuation_total': inventory_services.compute_total_valuation(),
        'top_consumed': list(consumed_rows),
        'purchases_count': purchases_in_range.count(),
        'purchases_total': purchases_total,
    }


# ============================================================
# Suppliers
# ============================================================

def suppliers_report(start_date, end_date):
    purchases = Purchase.objects.filter(status=PurchaseStatus.RECEIVED, received_date__range=[start_date, end_date])

    totals_by_supplier = {}
    for purchase in purchases.select_related('supplier'):
        entry = totals_by_supplier.setdefault(purchase.supplier_id, {
            'supplier': purchase.supplier, 'order_count': 0, 'total_value': Decimal('0.00'),
        })
        entry['order_count'] += 1
        entry['total_value'] += purchase.total_amount

    rows = sorted(totals_by_supplier.values(), key=lambda r: r['total_value'], reverse=True)

    return {'rows': rows, 'active_supplier_count': Supplier.objects.filter(is_active=True).count()}
