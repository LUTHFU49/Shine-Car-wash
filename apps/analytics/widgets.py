"""
The catalog of widgets a user can add to their Analytics dashboard
(see apps.analytics.models.DashboardPreference). Every fetcher here
calls into apps.payments.services / apps.reports.services /
apps.inventory.services -- this module doesn't compute anything that
phase didn't already compute, it just packages a slice of it for a
small dashboard card.
"""
from django.utils import timezone


def _last_n_days(n=30):
    end = timezone.localdate()
    start = end - timezone.timedelta(days=n - 1)
    return start, end


def _revenue_trend_data():
    from apps.payments import services as payment_services
    start, end = _last_n_days(30)
    daily = payment_services.compute_daily_collections(start, end)
    return {'labels': [row['date'].strftime('%b %d') for row in daily], 'values': [float(row['total']) for row in daily]}


def _booking_trend_data():
    from apps.reports import services as report_services
    start, end = _last_n_days(30)
    data = report_services.bookings_report(start, end)
    return {'labels': [row['scheduled_date'].strftime('%b %d') for row in data['by_day']], 'values': [row['count'] for row in data['by_day']]}


def _peak_hours_data():
    from apps.reports import services as report_services
    start, end = _last_n_days(30)
    data = report_services.bookings_report(start, end)
    return {'labels': [f"{row['hour']}:00" for row in data['by_hour']], 'values': [row['count'] for row in data['by_hour']]}


def _top_services_data():
    from apps.reports import services as report_services
    start, end = _last_n_days(30)
    data = report_services.services_report(start, end)
    return {'rows': sorted(data['rows'], key=lambda r: r.revenue, reverse=True)[:5]}


def _top_employees_data():
    from apps.reports import services as report_services
    start, end = _last_n_days(30)
    data = report_services.employees_report(start, end)
    return {'rows': data['rows'][:5]}


def _inventory_usage_data():
    from apps.reports import services as report_services
    start, end = _last_n_days(30)
    data = report_services.inventory_summary_report(start, end)
    return {'rows': data['top_consumed'][:5]}


def _low_stock_data():
    from apps.reports import services as report_services
    start, end = _last_n_days(30)
    data = report_services.inventory_summary_report(start, end)
    return {'items': data['low_stock_items'][:6], 'count': data['low_stock_count']}


def _satisfaction_data():
    from apps.feedback import services as feedback_services
    start, end = _last_n_days(30)
    summary = feedback_services.satisfaction_summary(start, end)
    return summary


def _recent_reviews_data():
    from apps.feedback.models import Review
    start, end = _last_n_days(30)
    reviews = Review.objects.filter(created_at__date__range=[start, end]).select_related('booking', 'customer').order_by('-created_at')[:5]
    return {'reviews': reviews}


WIDGET_CATALOG = [
    {
        'key': 'revenue_trend', 'title': 'Revenue (Last 30 Days)', 'icon': 'fa-chart-area',
        'template': 'analytics/widgets/chart.html', 'chart_type': 'bar', 'color': '#0013DE', 'span': 'lg:col-span-2',
        'fetch': _revenue_trend_data,
    },
    {
        'key': 'booking_trend', 'title': 'Booking Volume (Last 30 Days)', 'icon': 'fa-calendar-check',
        'template': 'analytics/widgets/chart.html', 'chart_type': 'line', 'color': '#FF0090', 'span': 'lg:col-span-2',
        'fetch': _booking_trend_data,
    },
    {
        'key': 'peak_hours', 'title': 'Peak Hours (Last 30 Days)', 'icon': 'fa-clock',
        'template': 'analytics/widgets/chart.html', 'chart_type': 'bar', 'color': '#5B69FF', 'span': '',
        'fetch': _peak_hours_data,
    },
    {
        'key': 'top_services', 'title': 'Most Popular Services', 'icon': 'fa-soap',
        'template': 'analytics/widgets/top_services.html', 'span': '',
        'fetch': _top_services_data,
    },
    {
        'key': 'top_employees', 'title': 'Employee Performance', 'icon': 'fa-user-tie',
        'template': 'analytics/widgets/top_employees.html', 'span': '',
        'fetch': _top_employees_data,
    },
    {
        'key': 'inventory_usage', 'title': 'Inventory Usage', 'icon': 'fa-boxes-stacked',
        'template': 'analytics/widgets/inventory_usage.html', 'span': '',
        'fetch': _inventory_usage_data,
    },
    {
        'key': 'low_stock', 'title': 'Low Stock Alert', 'icon': 'fa-triangle-exclamation',
        'template': 'analytics/widgets/low_stock.html', 'span': '',
        'fetch': _low_stock_data,
    },
    {
        'key': 'satisfaction', 'title': 'Customer Satisfaction', 'icon': 'fa-star',
        'template': 'analytics/widgets/satisfaction.html', 'span': '',
        'fetch': _satisfaction_data,
    },
    {
        'key': 'recent_reviews', 'title': 'Recent Reviews', 'icon': 'fa-comment-dots',
        'template': 'analytics/widgets/recent_reviews.html', 'span': '',
        'fetch': _recent_reviews_data,
    },
]

WIDGET_BY_KEY = {widget['key']: widget for widget in WIDGET_CATALOG}
DEFAULT_WIDGET_KEYS = [widget['key'] for widget in WIDGET_CATALOG]


def get_visible_widgets(keys):
    """Resolves stored widget keys to their catalog entries (in the
    order given), silently dropping any key that no longer exists in
    case the catalog ever changes."""
    return [WIDGET_BY_KEY[key] for key in keys if key in WIDGET_BY_KEY]
