from django.urls import path
from . import views

app_name = 'organizations'

urlpatterns = [
    path('',                views.settings_home,   name='settings'),
    path('receipt-preview/', views.receipt_preview, name='receipt_preview'),
]
