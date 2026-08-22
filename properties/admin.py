from django.contrib import admin
from .models import Property, HouseType, Unit


class HouseTypeInline(admin.TabularInline):
    model = HouseType
    extra = 1
    fields = ['name', 'default_rent', 'default_deposit', 'description']


class UnitInline(admin.TabularInline):
    model = Unit
    extra = 1
    fields = ['unit_number', 'house_type', 'floor',
              'rent_amount', 'deposit_amount', 'status']


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'city',
                    'status', 'total_units', 'created_at']
    list_filter = ['status', 'city']
    search_fields = ['name', 'code', 'address']
    readonly_fields = ['id', 'slug', 'created_at', 'updated_at']
    inlines = [HouseTypeInline]

    fieldsets = (
        ('Identity',    {
         'fields': ('id', 'organization', 'name', 'slug', 'code')}),
        ('Location',    {'fields': ('address', 'city', 'county', 'country')}),
        ('Details',     {'fields': ('description', 'image', 'total_units')}),
        ('Status',      {'fields': ('status',)}),
        ('Timestamps',  {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(HouseType)
class HouseTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'prop', 'default_rent', 'default_deposit']
    list_filter = ['prop']
    search_fields = ['name', 'prop__name']


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ['unit_number', 'prop', 'house_type', 'status',
                    'rent_amount', 'deposit_amount', 'is_archived']
    list_filter = ['status', 'prop', 'is_archived']
    search_fields = ['unit_number', 'prop__name']
    readonly_fields = ['id', 'created_at', 'updated_at']
