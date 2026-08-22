from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Payments
    path('',                       views.payment_list,   name='payment_list'),
    path('payments/record/',       views.payment_record, name='payment_record'),
    path('payments/<uuid:pk>/',    views.payment_detail, name='payment_detail'),

    # Verification workflow (§20/§28)
    path('verification/',                 views.verification_queue, name='verification_queue'),
    path('payments/<uuid:pk>/verify/',    views.payment_verify,     name='payment_verify'),
    path('payments/<uuid:pk>/reject/',    views.payment_reject,     name='payment_reject'),

    # Rent generation
    path('generate-rent/',         views.generate_rent,  name='generate_rent'),

    # Arrears
    path('arrears/',               views.arrears_dashboard, name='arrears'),

    # Statement + charges/adjustments (per tenancy)
    path('statement/<uuid:tenancy_pk>/',           views.tenant_statement, name='tenant_statement'),
    path('tenancy/<uuid:tenancy_pk>/charge/add/',  views.charge_add,       name='charge_add'),
    path('tenancy/<uuid:tenancy_pk>/adjustment/add/', views.adjustment_add, name='adjustment_add'),
]
