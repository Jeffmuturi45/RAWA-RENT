from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # Redirect root to dashboard
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),

    # Core
    path('', include('core.urls')),

    # Accounts
    path('accounts/', include('accounts.urls')),

    # Properties
    path('properties/', include('properties.urls')),

    # Tenants
    path('tenants/', include('tenants.urls')),

    # Tenancies
    path('tenancies/', include('tenancies.urls')),

    # Notifications
    path('notifications/', include('notifications.urls')),

    # Finance
    path('finance/', include('finance.urls')),

    # Receipts
    path('receipts/', include('receipts.urls')),

    # Settings (agency/organization)
    path('settings/', include('organizations.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL,
                          document_root=settings.STATIC_ROOT)
