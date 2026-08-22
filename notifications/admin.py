from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'message', 'level', 'is_read', 'created_at']
    list_filter = ['level', 'is_read', 'organization']
    search_fields = ['recipient__full_name', 'recipient__email', 'message']
    readonly_fields = ['id', 'created_at']
