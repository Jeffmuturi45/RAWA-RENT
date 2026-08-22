from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'full_name', 'role',
                    'organization', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'is_staff']
    search_fields = ['email', 'full_name', 'phone']
    ordering = ['full_name']

    fieldsets = (
        ('Identity',    {
         'fields': ('email', 'password', 'full_name', 'phone', 'avatar')}),
        ('Role',        {'fields': ('role', 'organization')}),
        ('Security',    {'fields': (
            'financial_pin', 'must_change_password', 'failed_login_attempts', 'locked_until')}),
        ('Permissions', {'fields': ('is_active', 'is_staff',
         'is_superuser', 'groups', 'user_permissions')}),
        ('Timestamps',  {
         'fields': ('last_login', 'created_at', 'updated_at')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'role', 'organization', 'password1', 'password2'),
        }),
    )

    readonly_fields = ['created_at', 'updated_at', 'last_login']
