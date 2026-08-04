from django.contrib import admin

from .models import Invoice, Payment, Refund


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    fields = ('method', 'amount', 'status', 'mpesa_receipt_number', 'created_at')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'booking', 'total_amount', 'amount_paid', 'balance', 'status', 'issued_date')
    list_filter = ('status', 'issued_date')
    search_fields = ('booking__vehicle__license_plate', 'booking__customer__first_name', 'booking__customer__last_name')
    readonly_fields = ('public_id', 'amount_paid', 'created_at', 'updated_at')
    autocomplete_fields = ('booking', 'created_by')
    inlines = [PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'invoice', 'method', 'amount', 'status', 'mpesa_receipt_number', 'created_at')
    list_filter = ('method', 'status', 'created_at')
    search_fields = ('mpesa_receipt_number', 'checkout_request_id', 'phone_number', 'invoice__booking__vehicle__license_plate')
    autocomplete_fields = ('invoice', 'initiated_by')
    readonly_fields = [f.name for f in Payment._meta.fields]  # ledger-like -- never hand-edited from Admin

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'payment', 'amount', 'status', 'processed_by', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('payment__mpesa_receipt_number',)
    autocomplete_fields = ('payment', 'processed_by')
    readonly_fields = ('public_id', 'created_at')
