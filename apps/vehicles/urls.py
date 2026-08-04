from django.urls import path

from . import views

app_name = 'vehicles'

urlpatterns = [
    # Staff-facing
    path('', views.vehicle_list_view, name='list'),
    path('create/', views.vehicle_create_view, name='create'),
    path('export/csv/', views.vehicle_export_csv_view, name='export_csv'),
    path('export/excel/', views.vehicle_export_excel_view, name='export_excel'),
    path('<uuid:public_id>/', views.vehicle_detail_view, name='detail'),
    path('<uuid:public_id>/edit/', views.vehicle_edit_view, name='edit'),
    path('<uuid:public_id>/status/<str:new_status>/', views.vehicle_set_status_view, name='set_status'),

    # Customer self-service ("My Vehicles")
    path('my/', views.my_vehicles_list_view, name='my_list'),
    path('my/add/', views.my_vehicle_create_view, name='my_create'),
    path('my/<uuid:public_id>/edit/', views.my_vehicle_edit_view, name='my_edit'),
    path('my/<uuid:public_id>/mark-sold/', views.my_vehicle_mark_sold_view, name='my_mark_sold'),
]
