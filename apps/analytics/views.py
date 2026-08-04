from django.contrib import messages
from django.shortcuts import redirect, render

from apps.core.decorators import management_required
from apps.reports import exports

from . import services
from .models import DashboardPreference
from .widgets import DEFAULT_WIDGET_KEYS, WIDGET_CATALOG, get_visible_widgets


def _get_or_create_preference(user):
    preference, created = DashboardPreference.objects.get_or_create(
        user=user, defaults={'visible_widgets': DEFAULT_WIDGET_KEYS},
    )
    return preference


@management_required
def dashboard_view(request):
    preference = _get_or_create_preference(request.user)
    widgets = get_visible_widgets(preference.visible_widgets)

    rendered_widgets = []
    for widget in widgets:
        rendered_widgets.append({**widget, 'data': widget['fetch']()})

    return render(request, 'analytics/dashboard.html', {
        'kpis': services.compute_kpis(),
        'widgets': rendered_widgets,
    })


@management_required
def customize_view(request):
    preference = _get_or_create_preference(request.user)

    if request.method == 'POST':
        selected = request.POST.getlist('widgets')
        # Keep catalog order rather than form submission order, so the
        # dashboard layout stays stable regardless of checkbox order.
        ordered = [w['key'] for w in WIDGET_CATALOG if w['key'] in selected]
        preference.visible_widgets = ordered
        preference.save(update_fields=['visible_widgets', 'updated_at'])
        messages.success(request, 'Dashboard updated.')
        return redirect('analytics:dashboard')

    return render(request, 'analytics/customize.html', {
        'catalog': WIDGET_CATALOG,
        'visible_keys': set(preference.visible_widgets),
    })


@management_required
def monthly_summary_view(request):
    rows = services.monthly_summary(months=12)
    return render(request, 'analytics/monthly_summary.html', {'rows': rows})


@management_required
def monthly_summary_export_view(request):
    rows = services.monthly_summary(months=12)
    headers = ['Month', 'Revenue (KSh)', 'Profit (KSh)', 'Bookings', 'Completed', 'New Customers']
    export_rows = [[r['label'], r['revenue'], r['profit'], r['bookings'], r['completed_bookings'], r['new_customers']] for r in rows]
    fmt = request.GET.get('format', 'csv').lower()
    if fmt == 'excel':
        return exports.excel_response('shinehub-monthly-summary', 'Monthly Summary', headers, export_rows)
    if fmt == 'pdf':
        return exports.pdf_response('shinehub-monthly-summary', 'Monthly Summary', 'Last 12 months', headers, export_rows)
    return exports.csv_response('shinehub-monthly-summary', headers, export_rows)


@management_required
def yearly_summary_view(request):
    rows = services.yearly_summary(years=5)
    return render(request, 'analytics/yearly_summary.html', {'rows': rows})


@management_required
def yearly_summary_export_view(request):
    rows = services.yearly_summary(years=5)
    headers = ['Year', 'Revenue (KSh)', 'Profit (KSh)', 'Bookings', 'Completed', 'New Customers']
    export_rows = [[r['label'], r['revenue'], r['profit'], r['bookings'], r['completed_bookings'], r['new_customers']] for r in rows]
    fmt = request.GET.get('format', 'csv').lower()
    if fmt == 'excel':
        return exports.excel_response('shinehub-yearly-summary', 'Yearly Summary', headers, export_rows)
    if fmt == 'pdf':
        return exports.pdf_response('shinehub-yearly-summary', 'Yearly Summary', 'Last 5 years', headers, export_rows)
    return exports.csv_response('shinehub-yearly-summary', headers, export_rows)
