from django.contrib import admin
from .models import Receipt


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'payment', 'issued_at', 'issued_by']
    list_filter = ['organization']
    search_fields = ['receipt_number', 'payment__tenant__full_name']
    readonly_fields = ['id', 'receipt_number', 'payment', 'issued_at', 'issued_by']
