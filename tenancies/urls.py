from django.urls import path
from . import views

app_name = 'tenancies'

urlpatterns = [
    path('',           views.tenancy_list,   name='list'),
    path('new/',       views.tenancy_create, name='create'),
    path('<uuid:pk>/', views.tenancy_detail, name='detail'),
]
