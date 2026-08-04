from django.urls import path

from . import views

app_name = 'analytics'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('customize/', views.customize_view, name='customize'),
    path('monthly/', views.monthly_summary_view, name='monthly'),
    path('monthly/export/', views.monthly_summary_export_view, name='monthly_export'),
    path('yearly/', views.yearly_summary_view, name='yearly'),
    path('yearly/export/', views.yearly_summary_export_view, name='yearly_export'),
]
