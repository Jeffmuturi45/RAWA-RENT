from django.urls import path
from . import views

app_name = 'tenants'

urlpatterns = [
    path('',                views.tenant_list,   name='list'),
    path('add/',            views.tenant_create, name='create'),
    path('<uuid:pk>/',      views.tenant_detail, name='detail'),
    path('<uuid:pk>/edit/', views.tenant_edit,   name='edit'),
]
