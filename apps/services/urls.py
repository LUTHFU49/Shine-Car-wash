from django.urls import path

from . import views

app_name = 'services'

urlpatterns = [
    # Public catalog
    path('', views.service_catalog_view, name='catalog'),

    # Staff: services
    path('manage/', views.service_list_view, name='list'),
    path('manage/create/', views.service_create_view, name='create'),
    path('manage/export/csv/', views.service_export_csv_view, name='export_csv'),
    path('manage/export/excel/', views.service_export_excel_view, name='export_excel'),
    path('manage/<uuid:public_id>/', views.service_detail_view, name='detail'),
    path('manage/<uuid:public_id>/edit/', views.service_edit_view, name='edit'),
    path('manage/<uuid:public_id>/status/<str:new_status>/', views.service_set_status_view, name='set_status'),

    # Staff: service categories
    path('manage/categories/', views.category_list_view, name='category_list'),
    path('manage/categories/create/', views.category_create_view, name='category_create'),
    path('manage/categories/<uuid:public_id>/edit/', views.category_edit_view, name='category_edit'),
    path('manage/categories/<uuid:public_id>/status/<str:new_status>/', views.category_set_status_view, name='category_set_status'),
]
