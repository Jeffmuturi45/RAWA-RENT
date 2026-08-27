from django.urls import path
from . import views

app_name = 'portal'

urlpatterns = [
    # ── Dashboard ──────────────────────────────────────────
    path('',                            views.portal_dashboard,
         name='dashboard'),

    # ── Statement ──────────────────────────────────────────
    path('statement/',                  views.portal_statement,
         name='statement'),

    # ── Payments ───────────────────────────────────────────
    path('payments/',                   views.portal_payments,
         name='payments'),

    # ── Receipts ───────────────────────────────────────────
    path('receipts/',                   views.portal_receipts,
         name='receipts'),
    path('receipts/<uuid:pk>/',
         views.portal_receipt_detail,    name='receipt_detail'),
    path('receipts/<uuid:pk>/pdf/',
         views.portal_receipt_pdf,       name='receipt_pdf'),

    # ── Deposit ────────────────────────────────────────────
    path('deposit/',                    views.portal_deposit,           name='deposit'),

    # ── Rent Notices (proof of payment) ────────────────────
    path('notices/',                    views.portal_notices,           name='notices'),
    path('notices/<uuid:pk>/upload/',
         views.portal_notice_upload,     name='notice_upload'),

    # ── Maintenance Requests ───────────────────────────────
    path('maintenance/',                views.portal_maintenance,
         name='maintenance'),
    path('maintenance/create/',         views.portal_maintenance_create,
         name='maintenance_create'),
    path('maintenance/<uuid:pk>/',
         views.portal_maintenance_detail, name='maintenance_detail'),
    path('maintenance/<uuid:pk>/rate/',
         views.portal_maintenance_rate,   name='maintenance_rate'),

    # ── Move-Out Request ───────────────────────────────────
    path('moveout/',                    views.portal_moveout,           name='moveout'),
    path('moveout/create/',             views.portal_moveout_create,
         name='moveout_create'),
    path('moveout/<uuid:pk>/',
         views.portal_moveout_detail,    name='moveout_detail'),

    # ── Transfer Request ───────────────────────────────────
    path('transfer/',                   views.portal_transfer,
         name='transfer'),
    path('transfer/create/',            views.portal_transfer_create,
         name='transfer_create'),

    # ── Notifications ──────────────────────────────────────
    path('notifications/',
         views.portal_notifications,             name='notifications'),
    path('notifications/<uuid:pk>/read/',
         views.portal_notification_mark_read,    name='notification_mark_read'),
    path('notifications/mark-all-read/',
         views.portal_notifications_mark_all_read, name='notifications_mark_all_read'),
]
