from django.urls import path
from . import views

app_name = 'portal'

urlpatterns = [
    path('',                        views.portal_dashboard,  name='dashboard'),
    path('statement/',              views.portal_statement,  name='statement'),
    path('payments/',               views.portal_payments,   name='payments'),
    path('receipts/',               views.portal_receipts,   name='receipts'),
    path('receipts/<uuid:pk>/',
         views.portal_receipt_detail, name='receipt_detail'),
    path('receipts/<uuid:pk>/pdf/',
         views.portal_receipt_pdf,    name='receipt_pdf'),
    path('deposit/',                views.portal_deposit,    name='deposit'),
    path('profile/',                views.portal_profile,    name='profile'),
]
