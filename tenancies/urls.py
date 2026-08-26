from django.urls import path
from . import views

app_name = 'tenancies'

urlpatterns = [
    path('',                                    views.tenancy_list,      name='list'),
    path('new/',
         views.tenancy_create,    name='create'),
    path('<uuid:pk>/',
         views.tenancy_detail,    name='detail'),
    path('<uuid:pk>/transfer/',
         views.transfer_initiate, name='transfer_initiate'),
    path('<uuid:pk>/transfer/confirm/',
         views.transfer_confirm,  name='transfer_confirm'),
    path('<uuid:pk>/move-out/',
         views.moveout_create,    name='moveout'),
]
