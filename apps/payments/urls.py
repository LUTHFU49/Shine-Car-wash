from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),

    # Transactions
    path('transactions/', views.payment_list_view, name='payment_list'),
    path('transactions/export/csv/', views.payment_export_csv_view, name='payment_export_csv'),
    path('transactions/export/excel/', views.payment_export_excel_view, name='payment_export_excel'),
    path('transactions/<uuid:public_id>/', views.payment_detail_view, name='payment_detail'),
    path('transactions/<uuid:public_id>/receipt/', views.payment_receipt_pdf_view, name='payment_receipt_pdf'),
    path('transactions/<uuid:public_id>/verify/', views.payment_verify_view, name='payment_verify'),
    path('transactions/<uuid:public_id>/refund/', views.payment_refund_view, name='payment_refund'),

    # Invoices
    path('invoices/', views.invoice_list_view, name='invoice_list'),
    path('invoices/<uuid:public_id>/', views.invoice_detail_view, name='invoice_detail'),
    path('invoices/<uuid:public_id>/pdf/', views.invoice_pdf_view, name='invoice_pdf'),
    path('invoices/<uuid:public_id>/void/', views.invoice_void_view, name='invoice_void'),
    path('invoices/<uuid:public_id>/record-cash/', views.invoice_record_cash_view, name='invoice_record_cash'),
    path('invoices/<uuid:public_id>/initiate-mpesa/', views.invoice_initiate_mpesa_view, name='invoice_initiate_mpesa'),

    # Daily collections / revenue
    path('collections/', views.collections_view, name='collections'),
    path('collections/export/csv/', views.collections_export_csv_view, name='collections_export_csv'),

    # M-Pesa callback
    path('mpesa/callback/', views.mpesa_callback_view, name='mpesa_callback'),

    # Customer self-service
    path('my/<uuid:booking_public_id>/pay/', views.my_pay_view, name='my_pay'),
    path('my/payment/<uuid:public_id>/status/', views.my_payment_status_view, name='my_payment_status'),
    path('my/payment/<uuid:public_id>/poll/', views.my_payment_poll_view, name='my_payment_poll'),
]
