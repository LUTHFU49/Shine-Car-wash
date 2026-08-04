from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),

    # Items
    path('items/', views.item_list_view, name='item_list'),
    path('items/create/', views.item_create_view, name='item_create'),
    path('items/import/', views.item_csv_import_view, name='item_csv_import'),
    path('items/export/csv/', views.item_export_csv_view, name='item_export_csv'),
    path('items/export/excel/', views.item_export_excel_view, name='item_export_excel'),
    path('items/export/pdf/', views.item_export_pdf_view, name='item_export_pdf'),
    path('items/print/', views.item_print_report_view, name='item_print_report'),
    path('items/bulk-action/', views.item_bulk_action_view, name='item_bulk_action'),
    path('items/<uuid:public_id>/', views.item_detail_view, name='item_detail'),
    path('items/<uuid:public_id>/edit/', views.item_edit_view, name='item_edit'),
    path('items/<uuid:public_id>/status/<str:new_status>/', views.item_set_status_view, name='item_set_status'),
    path('items/<uuid:public_id>/adjust/', views.item_adjust_stock_view, name='item_adjust_stock'),
    path('items/<uuid:public_id>/damage/', views.item_report_damage_view, name='item_report_damage'),

    # Categories
    path('categories/', views.category_list_view, name='category_list'),
    path('categories/create/', views.category_create_view, name='category_create'),
    path('categories/<uuid:public_id>/edit/', views.category_edit_view, name='category_edit'),
    path('categories/<uuid:public_id>/status/<str:new_status>/', views.category_set_status_view, name='category_set_status'),

    # Suppliers
    path('suppliers/', views.supplier_list_view, name='supplier_list'),
    path('suppliers/create/', views.supplier_create_view, name='supplier_create'),
    path('suppliers/<uuid:public_id>/edit/', views.supplier_edit_view, name='supplier_edit'),
    path('suppliers/<uuid:public_id>/status/<str:new_status>/', views.supplier_set_status_view, name='supplier_set_status'),

    # Purchases
    path('purchases/', views.purchase_list_view, name='purchase_list'),
    path('purchases/create/', views.purchase_create_view, name='purchase_create'),
    path('purchases/<uuid:public_id>/', views.purchase_detail_view, name='purchase_detail'),
    path('purchases/<uuid:public_id>/edit/', views.purchase_edit_view, name='purchase_edit'),
    path('purchases/<uuid:public_id>/receive/', views.purchase_receive_view, name='purchase_receive'),
    path('purchases/<uuid:public_id>/cancel/', views.purchase_cancel_view, name='purchase_cancel'),
    path('purchases/<uuid:public_id>/export/pdf/', views.purchase_export_pdf_view, name='purchase_export_pdf'),

    # Stock movement ledger
    path('movements/', views.movement_list_view, name='movement_list'),
    path('movements/export/csv/', views.movement_export_csv_view, name='movement_export_csv'),

    # Service <-> Inventory requirements
    path('requirements/', views.requirement_list_view, name='requirement_list'),
    path('requirements/create/', views.requirement_create_view, name='requirement_create'),
    path('requirements/<int:pk>/delete/', views.requirement_delete_view, name='requirement_delete'),
]
