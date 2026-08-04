from django.urls import path

from . import views

app_name = 'feedback'

urlpatterns = [
    # Customer self-service
    path('my/', views.my_list_view, name='my_list'),
    path('my/submit/', views.submit_feedback_view, name='my_submit'),
    path('my/booking/<uuid:booking_public_id>/review/', views.submit_review_view, name='submit_review'),

    # Staff: Reviews
    path('reviews/', views.review_list_view, name='review_list'),
    path('reviews/<uuid:public_id>/', views.review_detail_view, name='review_detail'),
    path('reviews/<uuid:public_id>/respond/', views.review_respond_view, name='review_respond'),
    path('reviews/<uuid:public_id>/status/<str:new_status>/', views.review_set_published_view, name='review_set_published'),

    # Staff: Feedback
    path('complaints/', views.feedback_list_view, name='feedback_list'),
    path('complaints/<uuid:public_id>/', views.feedback_detail_view, name='feedback_detail'),
    path('complaints/<uuid:public_id>/respond/', views.feedback_respond_view, name='feedback_respond'),

    # Staff: Satisfaction analytics
    path('satisfaction/', views.satisfaction_view, name='satisfaction'),
    path('satisfaction/export/', views.satisfaction_export_view, name='satisfaction_export'),
]
