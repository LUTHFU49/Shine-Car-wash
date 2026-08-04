"""
Root URL configuration for the ShineHub project.

Phase 1 wires up: admin, core (landing page + static pages), and accounts
(auth placeholders — full views land in Phase 2). Every other app gets
its urls.py included now (even if mostly empty) so the include() chain
never needs to change shape again — only the contents of each app's
urls.py grow phase by phase.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', include('apps.core.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('dashboard/', include('apps.dashboard.urls')),
    path('customers/', include('apps.customers.urls')),
    path('vehicles/', include('apps.vehicles.urls')),
    path('services/', include('apps.services.urls')),
    path('bookings/', include('apps.bookings.urls')),
    path('payments/', include('apps.payments.urls')),
    path('inventory/', include('apps.inventory.urls')),
    path('employees/', include('apps.employees.urls')),
    path('reports/', include('apps.reports.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('settings/', include('apps.site_settings.urls')),
    path('feedback/', include('apps.feedback.urls')),
    path('loyalty/', include('apps.loyalty.urls')),
    path('analytics/', include('apps.analytics.urls')),
]

handler403 = 'apps.core.views.error_403'
handler404 = 'apps.core.views.error_404'
handler500 = 'apps.core.views.error_500'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
