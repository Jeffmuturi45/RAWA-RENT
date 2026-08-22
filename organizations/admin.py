from django.contrib import admin
from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'phone', 'city', 'status', 'created_at']
    list_filter = ['status', 'country']
    search_fields = ['name', 'email', 'phone']
    readonly_fields = ['id', 'created_at', 'updated_at']

    fieldsets = (
        ('Identity',    {'fields': ('id', 'name', 'slug', 'registration_no')}),
        ('Contact',     {'fields': ('phone', 'email',
         'website', 'address', 'city', 'country')}),
        ('Branding',    {'fields': ('logo', 'favicon', 'footer_text')}),
        ('Theme',       {'fields': (
            'theme_primary', 'theme_secondary', 'theme_accent',
            'theme_dark', 'theme_light', 'theme_success',
            'theme_warning', 'theme_danger', 'theme_text_primary',
            'theme_text_secondary', 'theme_border'
        )}),
        ('System',      {
         'fields': ('receipt_size', 'cutover_date', 'status')}),
        ('Timestamps',  {'fields': ('created_at', 'updated_at')}),
    )
