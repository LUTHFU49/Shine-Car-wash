from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.hub_view, name='hub'),

    path('revenue/', views.revenue_report_view, name='revenue'),
    path('revenue/export/', views.revenue_report_export_view, name='revenue_export'),

    path('expenses-report/', views.expenses_report_view, name='expenses_report'),
    path('expenses-report/export/', views.expenses_report_export_view, name='expenses_report_export'),

    path('profit/', views.profit_report_view, name='profit'),
    path('profit/export/', views.profit_report_export_view, name='profit_export'),

    path('bookings/', views.bookings_report_view, name='bookings_report'),
    path('bookings/export/', views.bookings_report_export_view, name='bookings_report_export'),

    path('services/', views.services_report_view, name='services_report'),
    path('services/export/', views.services_report_export_view, name='services_report_export'),

    path('customers/', views.customers_report_view, name='customers_report'),
    path('customers/export/', views.customers_report_export_view, name='customers_report_export'),

    path('vehicles/', views.vehicles_report_view, name='vehicles_report'),
    path('vehicles/export/', views.vehicles_report_export_view, name='vehicles_report_export'),

    path('employees/', views.employees_report_view, name='employees_report'),
    path('employees/export/', views.employees_report_export_view, name='employees_report_export'),

    path('inventory/', views.inventory_report_view, name='inventory_report'),
    path('inventory/export/', views.inventory_report_export_view, name='inventory_report_export'),

    path('suppliers/', views.suppliers_report_view, name='suppliers_report'),
    path('suppliers/export/', views.suppliers_report_export_view, name='suppliers_report_export'),

    path('expenses/', views.expense_list_view, name='expense_list'),
    path('expenses/create/', views.expense_create_view, name='expense_create'),
    path('expenses/<uuid:public_id>/edit/', views.expense_edit_view, name='expense_edit'),
    path('expenses/<uuid:public_id>/status/<str:new_status>/', views.expense_set_status_view, name='expense_set_status'),

    path('expenses/categories/', views.expense_category_list_view, name='expense_category_list'),
    path('expenses/categories/create/', views.expense_category_create_view, name='expense_category_create'),
]
