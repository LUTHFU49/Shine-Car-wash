from django.urls import path

from . import views

app_name = 'employees'

urlpatterns = [
    # Staff-facing (Super Admin / Manager)
    path('', views.employee_list_view, name='list'),
    path('create/', views.employee_create_view, name='create'),
    path('export/csv/', views.employee_export_csv_view, name='export_csv'),
    path('export/excel/', views.employee_export_excel_view, name='export_excel'),
    path('<uuid:public_id>/', views.employee_detail_view, name='detail'),
    path('<uuid:public_id>/edit/', views.employee_edit_view, name='edit'),
    path('<uuid:public_id>/attendance/add/', views.attendance_create_view, name='attendance_create'),
    path('<uuid:public_id>/reviews/add/', views.performance_review_create_view, name='review_create'),

    # Employee self-service (read-only)
    path('my/profile/', views.my_profile_view, name='my_profile'),
    path('my/attendance/', views.my_attendance_view, name='my_attendance'),
    path('my/performance/', views.my_performance_view, name='my_performance'),
    path('my/assignments/', views.my_assignments_view, name='my_assignments'),
]
