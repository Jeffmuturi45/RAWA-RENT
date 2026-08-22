from django.urls import path
from . import views

app_name = 'properties'

urlpatterns = [
    # Properties
    path('',                            views.property_list,    name='list'),
    path('add/',                        views.property_create,  name='create'),
    path('<uuid:pk>/',                  views.property_detail,  name='detail'),
    path('<uuid:pk>/edit/',             views.property_edit,    name='edit'),

    # House Types
    path('<uuid:property_pk>/house-types/add/',
         views.house_type_create, name='house_type_create'),
    path('house-types/<uuid:pk>/edit/',
         views.house_type_edit,   name='house_type_edit'),

    # Units
    path('units/',
         views.unit_list,   name='unit_list'),
    path('<uuid:property_pk>/units/add/',
         views.unit_create,  name='unit_create'),
    path('units/<uuid:pk>/',
         views.unit_detail,  name='unit_detail'),
    path('units/<uuid:pk>/edit/',
         views.unit_edit,    name='unit_edit'),
]
