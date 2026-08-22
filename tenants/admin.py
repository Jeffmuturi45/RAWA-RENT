from django.contrib import admin
from .models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['tenant_number', 'full_name', 'phone', 'email',
                    'status', 'created_at']
    list_filter = ['status', 'organization']
    search_fields = ['tenant_number', 'full_name', 'phone',
                     'email', 'national_id']
    readonly_fields = ['id', 'tenant_number', 'created_at', 'updated_at']

    fieldsets = (
        ('Identity',          {'fields': ('id', 'organization', 'tenant_number',
                                          'full_name', 'phone', 'email',
                                          'national_id', 'date_of_birth')}),
        ('Emergency Contact', {'fields': ('emergency_contact', 'emergency_phone',
                                          'emergency_relation')}),
        ('Address',           {'fields': ('address',)}),
        ('Documents',         {'fields': ('id_document', 'photo')}),
        ('Portal',            {'fields': ('user',)}),
        ('Status',            {'fields': ('status', 'notes')}),
        ('Timestamps',        {'fields': ('created_at', 'updated_at')}),
    )
