from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('password/forgot/', views.forgot_password_view, name='password_reset'),
    path('password/reset/<uidb64>/<token>/', views.password_reset_confirm_view, name='password_reset_confirm'),

    path('verify-email/<uuid:token>/', views.verify_email_view, name='verify_email'),
    path('verify-email/resend/', views.resend_verification_view, name='resend_verification'),

    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),
    path('profile/photo/upload/', views.profile_photo_upload_view, name='profile_photo_upload'),
    path('profile/photo/remove/', views.profile_photo_remove_view, name='profile_photo_remove'),
    path('profile/change-password/', views.change_password_view, name='change_password'),
    path('profile/delete/', views.delete_account_view, name='delete_account'),

    path('sessions/', views.active_sessions_view, name='active_sessions'),
    path('sessions/<int:session_pk>/revoke/', views.revoke_session_view, name='revoke_session'),
    path('sessions/revoke-others/', views.revoke_other_sessions_view, name='revoke_other_sessions'),
]
