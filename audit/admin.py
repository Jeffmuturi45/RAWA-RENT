from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'action', 'actor', 'object_type',
                    'object_repr', 'ip']
    list_filter = ['action', 'object_type', 'organization']
    search_fields = ['action', 'object_repr', 'object_id',
                     'actor__full_name', 'actor__email']
    readonly_fields = ['id', 'organization', 'actor', 'action', 'object_type',
                       'object_id', 'object_repr', 'ip', 'before', 'after',
                       'reason', 'created_at']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
