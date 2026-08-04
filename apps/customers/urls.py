from django.urls import path

from . import views

app_name = 'customers'

urlpatterns = [
    path('', views.customer_list_view, name='list'),
    path('create/', views.customer_create_view, name='create'),
    path('export/csv/', views.customer_export_csv_view, name='export_csv'),
    path('export/excel/', views.customer_export_excel_view, name='export_excel'),
    path('<uuid:public_id>/', views.customer_detail_view, name='detail'),
    path('<uuid:public_id>/edit/', views.customer_edit_view, name='edit'),
    path('<uuid:public_id>/deactivate/', views.customer_deactivate_view, name='deactivate'),
    path('<uuid:public_id>/reactivate/', views.customer_reactivate_view, name='reactivate'),
]
