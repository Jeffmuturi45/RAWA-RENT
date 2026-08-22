from django.contrib import admin
from .models import (
    Charge, Payment, PaymentAllocation,
    DepositAccount, DepositMovement, Adjustment,
)


class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    readonly_fields = ['charge', 'amount', 'created_at']
    can_delete = False


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ['charge_type', 'tenancy', 'amount', 'due_date',
                    'is_opening_balance', 'created_at']
    list_filter = ['charge_type', 'is_opening_balance', 'organization']
    search_fields = ['tenancy__tenant__full_name', 'description']
    readonly_fields = ['id', 'created_at']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'amount', 'method', 'reference',
                    'status', 'payment_date', 'created_at']
    list_filter = ['status', 'method', 'organization']
    search_fields = ['tenant__full_name', 'reference']
    readonly_fields = ['id', 'created_at']
    inlines = [PaymentAllocationInline]


@admin.register(DepositAccount)
class DepositAccountAdmin(admin.ModelAdmin):
    list_display = ['tenancy', 'required_amount', 'created_at']
    search_fields = ['tenancy__tenant__full_name']
    readonly_fields = ['id', 'created_at']


@admin.register(DepositMovement)
class DepositMovementAdmin(admin.ModelAdmin):
    list_display = ['deposit_account', 'movement_type', 'amount', 'created_at']
    list_filter = ['movement_type']
    readonly_fields = ['id', 'created_at']


@admin.register(Adjustment)
class AdjustmentAdmin(admin.ModelAdmin):
    list_display = ['tenancy', 'direction', 'amount', 'effective_date', 'created_at']
    list_filter = ['direction', 'organization']
    readonly_fields = ['id', 'created_at']
