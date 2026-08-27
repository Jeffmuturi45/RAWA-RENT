# receipts/urls.py

from django.urls import path
from . import views

app_name = 'receipts'

urlpatterns = [
    path('', views.receipt_list, name='list'),
    path('issue/<uuid:payment_pk>/', views.receipt_issue, name='issue'),
    path('<uuid:pk>/', views.receipt_detail, name='detail'),
    path('<uuid:pk>/pdf/', views.receipt_pdf, name='pdf'),
]