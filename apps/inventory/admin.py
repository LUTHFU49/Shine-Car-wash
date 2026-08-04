from django.contrib import admin

from .models import (
    InventoryCategory, InventoryItem, ItemBatch, Purchase, PurchaseItem,
    ServiceInventoryRequirement, StockMovement, StockReservation, Supplier,
)


@admin.register(InventoryCategory)
class InventoryCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'display_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    readonly_fields = ('public_id', 'created_at', 'updated_at')


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'phone_number', 'email', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'contact_person', 'phone_number', 'email')
    readonly_fields = ('public_id', 'created_at', 'updated_at')


class ItemBatchInline(admin.TabularInline):
    model = ItemBatch
    extra = 0
    readonly_fields = ('quantity_received', 'quantity_remaining', 'unit_cost', 'received_date', 'purchase_item', 'created_at')
    can_delete = False


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'sku', 'category', 'unit', 'current_stock', 'reserved_stock',
        'available_stock', 'reorder_level', 'average_unit_cost', 'is_active',
    )
    list_filter = ('is_active', 'category', 'track_expiry', 'unit')
    search_fields = ('name', 'sku', 'description')
    readonly_fields = (
        'public_id', 'sku', 'current_stock', 'reserved_stock', 'average_unit_cost',
        'low_stock_alerted_at', 'created_at', 'updated_at',
    )
    autocomplete_fields = ('category', 'created_by')
    inlines = [ItemBatchInline]


@admin.register(ItemBatch)
class ItemBatchAdmin(admin.ModelAdmin):
    list_display = ('item', 'batch_number', 'quantity_received', 'quantity_remaining', 'expiry_date', 'is_expired')
    list_filter = ('expiry_date',)
    search_fields = ('item__name', 'batch_number')
    autocomplete_fields = ('item',)
    readonly_fields = ('created_at',)


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 1
    autocomplete_fields = ('item',)


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'supplier', 'status', 'order_date', 'received_date', 'total_amount')
    list_filter = ('status', 'supplier')
    search_fields = ('supplier__name',)
    readonly_fields = ('public_id', 'created_at', 'updated_at')
    autocomplete_fields = ('supplier', 'created_by')
    inlines = [PurchaseItemInline]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'item', 'movement_type', 'quantity', 'booking', 'performed_by')
    list_filter = ('movement_type', 'created_at')
    search_fields = ('item__name', 'item__sku', 'reason')
    autocomplete_fields = ('item', 'batch', 'booking', 'performed_by')
    readonly_fields = [f.name for f in StockMovement._meta.fields]  # append-only ledger -- never edited from Admin

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = ('booking', 'item', 'quantity', 'status', 'created_at')
    list_filter = ('status',)
    autocomplete_fields = ('booking', 'item')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ServiceInventoryRequirement)
class ServiceInventoryRequirementAdmin(admin.ModelAdmin):
    list_display = ('service', 'item', 'quantity_required')
    autocomplete_fields = ('service', 'item')
    search_fields = ('service__name', 'item__name')
