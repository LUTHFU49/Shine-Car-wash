from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('about/', views.about_page, name='about'),
    path('contact/', views.contact_page, name='contact'),
    path('faq/', views.faq_page, name='faq'),
    path('pricing/', views.pricing_page, name='pricing'),
]
