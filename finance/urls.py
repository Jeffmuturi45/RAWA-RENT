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
    
     # Rent Notices
    path('rent-notices/',                        views.rent_notice_list,          name='rent_notice_list'),
    path('rent-notices/<uuid:pk>/review/',       views.rent_notice_review,        name='rent_notice_review'),
    path('rent-notices/generate/',               views.trigger_rent_generation,   name='trigger_rent_generation'),
 
    # Maintenance Requests
    path('maintenance/',                         views.maintenance_list,          name='maintenance_list'),
    path('maintenance/<uuid:pk>/',               views.maintenance_detail,        name='maintenance_detail'),
 
    # Move-Out Requests
    path('moveout-requests/',                    views.moveout_request_list,      name='moveout_request_list'),
    path('moveout-requests/<uuid:pk>/',          views.moveout_request_detail,    name='moveout_request_detail'),
 
    # Transfer Requests
    path('transfer-requests/',                   views.transfer_request_list,     name='transfer_request_list'),
    path('transfer-requests/<uuid:pk>/',         views.transfer_request_detail,   name='transfer_request_detail'),
 
    # Vacancy
    path('vacancy/',                             views.vacancy_list,              name='vacancy_list'),
 
    # Dashboard KPI AJAX
    path('dashboard/kpis/',                      views.admin_dashboard_kpis,      name='dashboard_kpis'),
]
