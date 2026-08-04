from django.urls import path

from . import views

app_name = 'bookings'

urlpatterns = [
    # Customer self-service ("My Bookings")
    path('my/', views.my_bookings_list_view, name='my_list'),
    path('my/book/', views.my_booking_create_view, name='my_create'),
    path('my/<uuid:public_id>/', views.my_booking_detail_view, name='my_detail'),
    path('my/<uuid:public_id>/reschedule/', views.my_booking_reschedule_view, name='my_reschedule'),
    path('my/<uuid:public_id>/cancel/', views.my_booking_cancel_view, name='my_cancel'),

    # Staff-facing
    path('manage/', views.booking_list_view, name='list'),
    path('manage/create/', views.booking_create_view, name='create'),
    path('manage/calendar/', views.booking_calendar_view, name='calendar'),
    path('manage/queue/', views.booking_queue_view, name='queue'),
    path('manage/day/<str:date_str>/', views.booking_day_view, name='day'),
    path('manage/export/csv/', views.booking_export_csv_view, name='export_csv'),
    path('manage/export/excel/', views.booking_export_excel_view, name='export_excel'),
    path('manage/<uuid:public_id>/', views.booking_detail_view, name='detail'),
    path('manage/<uuid:public_id>/reschedule/', views.booking_reschedule_view, name='reschedule'),
    path('manage/<uuid:public_id>/cancel/', views.booking_cancel_view, name='cancel'),
    path('manage/<uuid:public_id>/assign/', views.booking_assign_employee_view, name='assign_employee'),
    path('manage/<uuid:public_id>/status/<str:new_status>/', views.booking_set_status_view, name='set_status'),
]
