"""
Phase 12 adds one genuinely new thing this project didn't have yet:
period-over-period KPI comparison and calendar month/year rollups.
Everything about *what* revenue, bookings, profit, and customers mean
already exists -- this module is a thin layer on top of
apps.payments.services.compute_revenue_summary and
apps.reports.services (expenses_report, profit_summary), not a
reimplementation of them.
"""
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.customers.models import Customer


def _month_bounds(year, month):
    start = timezone.datetime(year, month, 1).date()
    if month == 12:
        end = timezone.datetime(year, 12, 31).date()
    else:
        end = timezone.datetime(year, month + 1, 1).date() - timezone.timedelta(days=1)
    return start, end


def _shift_month(year, month, delta):
    index = (year * 12 + (month - 1)) + delta
    return index // 12, index % 12 + 1


def _year_bounds(year):
    return timezone.datetime(year, 1, 1).date(), timezone.datetime(year, 12, 31).date()


def _period_metrics(start_date, end_date):
    """Revenue, profit, bookings, and new customers for one date range --
    the four numbers every KPI/monthly/yearly view is built from."""
    from apps.payments import services as payment_services
    from apps.reports import services as report_services

    revenue = payment_services.compute_revenue_summary(start_date, end_date)
    profit = report_services.profit_summary(start_date, end_date)
    bookings_count = Booking.objects.filter(scheduled_date__range=[start_date, end_date]).count()
    completed_count = Booking.objects.filter(
        scheduled_date__range=[start_date, end_date], status=BookingStatus.COMPLETED,
    ).count()
    new_customers = Customer.objects.filter(created_at__date__range=[start_date, end_date]).count()

    return {
        'revenue': revenue['net_revenue'],
        'profit': profit['net_profit'],
        'bookings': bookings_count,
        'completed_bookings': completed_count,
        'new_customers': new_customers,
    }


def _trend(current, previous):
    if previous == 0:
        direction = 'flat' if current == 0 else 'up'
        return {'current': current, 'previous': previous, 'delta_pct': None, 'direction': direction}
    delta_pct = ((current - previous) / previous) * 100
    direction = 'up' if delta_pct > 0 else ('down' if delta_pct < 0 else 'flat')
    return {'current': current, 'previous': previous, 'delta_pct': round(float(delta_pct), 1), 'direction': direction}


def compute_kpis():
    """This-month-so-far vs the same span last month, for the four
    headline numbers shown at the top of the Analytics dashboard."""
    today = timezone.localdate()
    this_month_start = today.replace(day=1)

    prev_year, prev_month = _shift_month(today.year, today.month, -1)
    prev_month_start, prev_month_end_full = _month_bounds(prev_year, prev_month)
    # Compare like-for-like: only as many days into last month as we
    # are into this one, so a mid-month look isn't comparing a partial
    # month to a complete one.
    days_elapsed = (today - this_month_start).days
    prev_month_end = min(prev_month_start + timezone.timedelta(days=days_elapsed), prev_month_end_full)

    current = _period_metrics(this_month_start, today)
    previous = _period_metrics(prev_month_start, prev_month_end)

    return {
        'revenue': _trend(current['revenue'], previous['revenue']),
        'profit': _trend(current['profit'], previous['profit']),
        'bookings': _trend(current['bookings'], previous['bookings']),
        'new_customers': _trend(current['new_customers'], previous['new_customers']),
'period_label': f"{this_month_start.strftime('%b 1')}–{today.strftime('%b')} {today.day} vs same span last month",
    }


def monthly_summary(months=12):
    """One row per calendar month, most recent first."""
    today = timezone.localdate()
    rows = []
    for delta in range(months):
        year, month = _shift_month(today.year, today.month, -delta)
        start, full_end = _month_bounds(year, month)
        end = min(today, full_end) if (year, month) == (today.year, today.month) else full_end
        metrics = _period_metrics(start, end)
        rows.append({'label': start.strftime('%B %Y'), 'start': start, 'end': end, **metrics})
    return rows


def yearly_summary(years=5):
    """One row per calendar year, most recent first."""
    today = timezone.localdate()
    rows = []
    for delta in range(years):
        year = today.year - delta
        start, full_end = _year_bounds(year)
        end = min(today, full_end) if year == today.year else full_end
        metrics = _period_metrics(start, end)
        rows.append({'label': str(year), 'start': start, 'end': end, **metrics})
    return rows
