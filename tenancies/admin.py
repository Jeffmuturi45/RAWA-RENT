from django.contrib import admin
from .models import Tenancy, RentVariation


class RentVariationInline(admin.TabularInline):
    model = RentVariation
    extra = 0
    readonly_fields = ['previous_rent', 'new_rent', 'effective_date',
                       'created_by', 'approved_by', 'created_at']
    can_delete = False


@admin.register(Tenancy)
class TenancyAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'unit', 'monthly_rent', 'start_date',
                    'end_date', 'status', 'created_at']
    list_filter = ['status', 'organization']
    search_fields = ['tenant__full_name', 'tenant__tenant_number',
                     'unit__unit_number']
    readonly_fields = ['id', 'created_at', 'updated_at', 'created_by']
    inlines = [RentVariationInline]

    fieldsets = (
        ('Parties',     {'fields': ('id', 'organization', 'tenant', 'unit')}),
        ('Dates',       {'fields': ('start_date', 'end_date')}),
        ('Financials',  {'fields': ('monthly_rent',
         'required_deposit', 'billing_day')}),
        ('Status',      {'fields': ('status',
         'termination_reason', 'is_opening_balance')}),
        ('Audit',       {
         'fields': ('created_by', 'created_at', 'updated_at')}),
    )


@admin.register(RentVariation)
class RentVariationAdmin(admin.ModelAdmin):
    list_display = ['tenancy', 'previous_rent', 'new_rent',
                    'effective_date', 'created_at']
    readonly_fields = ['id', 'created_at', 'created_by']
