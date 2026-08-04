import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

# Font Awesome 6 icons curated for inventory categories -- kept as a fixed
# choice list (same convention as apps.services.models) so the inventory
# dashboard never ends up with a broken/mismatched icon class.
INVENTORY_CATEGORY_ICON_CHOICES = [
    ('fa-boxes-stacked', 'Boxes'),
    ('fa-pump-soap', 'Soap / Chemicals'),
    ('fa-spray-can-sparkles', 'Detailing Supplies'),
    ('fa-droplet', 'Liquids'),
    ('fa-brush', 'Brushes / Tools'),
    ('fa-shirt', 'Cloths / Fabric'),
    ('fa-oil-can', 'Oils / Lubricants'),
    ('fa-flask', 'Chemicals'),
    ('fa-toolbox', 'Equipment'),
    ('fa-box-open', 'Consumables'),
]


class InventoryUnit(models.TextChoices):
    PIECE = 'piece', 'Piece'
    BOTTLE = 'bottle', 'Bottle'
    LITRE = 'litre', 'Litre'
    MILLILITRE = 'ml', 'Millilitre'
    KILOGRAM = 'kg', 'Kilogram'
    GRAM = 'g', 'Gram'
    BOX = 'box', 'Box'
    PACK = 'pack', 'Pack'
    ROLL = 'roll', 'Roll'
    PAIR = 'pair', 'Pair'


class InventoryCategory(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    icon = models.CharField(max_length=30, choices=INVENTORY_CATEGORY_ICON_CHOICES, default='fa-boxes-stacked')
    display_order = models.PositiveIntegerField(default=0, help_text='Lower numbers appear first.')
    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_categories_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_category'
        ordering = ['display_order', 'name']
        verbose_name_plural = 'Inventory categories'

    def __str__(self):
        return self.name


class Supplier(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    name = models.CharField(max_length=150, unique=True)
    contact_person = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='suppliers_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_supplier'
        ordering = ['name']

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    """
    A stock-keeping unit. Never hard-deleted -- once Purchases/Stock
    Movements/Bookings reference an item, historical records need it to
    still resolve, hence `is_active` rather than delete (same convention
    as apps.services.Service).

    `current_stock`, `reserved_stock`, `average_unit_cost` and
    `low_stock_alerted_at` are maintained exclusively by
    apps.inventory.services -- never edited directly from a form.
    """
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    sku = models.CharField(max_length=30, unique=True, blank=True, editable=False)

    category = models.ForeignKey(InventoryCategory, on_delete=models.PROTECT, related_name='items')

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=10, choices=InventoryUnit.choices, default=InventoryUnit.PIECE)

    reorder_level = models.PositiveIntegerField(
        default=5, help_text='A low-stock alert fires when available stock falls to/below this level.',
    )
    track_expiry = models.BooleanField(
        default=False, help_text='If set, received stock is tracked in dated batches and consumed oldest-expiry-first.',
    )

    current_stock = models.PositiveIntegerField(default=0, editable=False)
    reserved_stock = models.PositiveIntegerField(default=0, editable=False, help_text='Held for confirmed bookings not yet completed.')
    average_unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, editable=False)
    low_stock_alerted_at = models.DateTimeField(blank=True, null=True, editable=False)

    image = models.ImageField(upload_to='inventory_photos/%Y/%m/', blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_items_created',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_item'
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return f'{self.name} ({self.sku})'

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = f'INV-{uuid.uuid4().hex[:8].upper()}'
        super().save(*args, **kwargs)

    @property
    def available_stock(self):
        return max(self.current_stock - self.reserved_stock, 0)

    @property
    def is_low_stock(self):
        return self.is_active and self.available_stock <= self.reorder_level

    @property
    def stock_value(self):
        return self.current_stock * self.average_unit_cost


class ItemBatch(models.Model):
    """
    A dated lot of stock received for an item with track_expiry=True.
    Consumption always draws from the earliest expiry_date first (see
    apps.inventory.services._consume_batches_fifo).
    """
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='batches')
    batch_number = models.CharField(max_length=50, blank=True)
    quantity_received = models.PositiveIntegerField()
    quantity_remaining = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    received_date = models.DateField(default=timezone.localdate)
    expiry_date = models.DateField(blank=True, null=True, db_index=True)
    purchase_item = models.ForeignKey(
        'PurchaseItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='batches',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_item_batch'
        ordering = ['expiry_date', 'received_date']

    def __str__(self):
        return f'{self.item.name} batch {self.batch_number or self.pk}'

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < timezone.localdate())


class PurchaseStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    ORDERED = 'ordered', 'Ordered'
    RECEIVED = 'received', 'Received'
    CANCELLED = 'cancelled', 'Cancelled'


class Purchase(models.Model):
    """A purchase order raised against a Supplier. Receiving it (see
    apps.inventory.services.receive_purchase) moves every line's quantity
    into stock in one transaction."""
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchases')
    status = models.CharField(max_length=10, choices=PurchaseStatus.choices, default=PurchaseStatus.DRAFT, db_index=True)

    order_date = models.DateField(default=timezone.localdate)
    expected_date = models.DateField(blank=True, null=True)
    received_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchases_created',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_purchase'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference_code} — {self.supplier.name}'

    @property
    def reference_code(self):
        return f'PO-{self.pk:06d}' if self.pk else 'PO-PENDING'

    @property
    def total_amount(self):
        return sum((line.line_total for line in self.items.all()), start=0)

    @property
    def is_editable(self):
        return self.status in (PurchaseStatus.DRAFT, PurchaseStatus.ORDERED)


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='purchase_items')
    quantity_ordered = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    quantity_received = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    expiry_date = models.DateField(
        blank=True, null=True, help_text='Only used if the item tracks expiry -- becomes the received batch expiry.',
    )

    class Meta:
        db_table = 'inventory_purchase_item'

    def __str__(self):
        return f'{self.item.name} x{self.quantity_ordered} ({self.purchase.reference_code})'

    @property
    def line_total(self):
        return self.quantity_ordered * self.unit_cost


class StockMovement(models.Model):
    """
    Append-only ledger. Nothing here is ever edited or deleted after
    creation -- it is the audit trail behind InventoryItem.current_stock
    and reserved_stock, which are denormalized for fast reads and kept in
    sync exclusively by apps.inventory.services.
    """
    class MovementType(models.TextChoices):
        PURCHASE_IN = 'purchase_in', 'Purchase Received'
        BOOKING_RESERVED = 'booking_reserved', 'Reserved for Booking'
        BOOKING_RELEASED = 'booking_released', 'Reservation Released'
        BOOKING_USED = 'booking_used', 'Used in Booking'
        ADJUSTMENT_IN = 'adjustment_in', 'Manual Adjustment (In)'
        ADJUSTMENT_OUT = 'adjustment_out', 'Manual Adjustment (Out)'
        DAMAGED = 'damaged', 'Damaged / Written Off'
        EXPIRED = 'expired', 'Expired / Written Off'
        RETURN_IN = 'return_in', 'Returned to Stock'

    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='movements')
    batch = models.ForeignKey(ItemBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=MovementType.choices, db_index=True)
    quantity = models.PositiveIntegerField(help_text='Always a positive magnitude; direction is implied by movement_type.')
    unit_cost_at_time = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    booking = models.ForeignKey(
        'bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_movements',
    )
    purchase_item = models.ForeignKey(
        PurchaseItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements',
    )
    reason = models.CharField(max_length=255, blank=True)

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'inventory_stock_movement'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['item', '-created_at'])]

    def __str__(self):
        return f'{self.get_movement_type_display()} — {self.item.name} x{self.quantity}'


class StockReservation(models.Model):
    class ReservationStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        CONSUMED = 'consumed', 'Consumed'
        RELEASED = 'released', 'Released'

    booking = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE, related_name='stock_reservations')
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='reservations')
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=ReservationStatus.choices, default=ReservationStatus.ACTIVE, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_stock_reservation'
        unique_together = [('booking', 'item')]

    def __str__(self):
        return f'{self.item.name} x{self.quantity} for {self.booking_id}'


class ServiceInventoryRequirement(models.Model):
    """Defines how much of an InventoryItem a Service consumes per booking.
    A Service with no rows here simply triggers no automatic stock
    movement -- existing services keep working exactly as before."""
    service = models.ForeignKey('services.Service', on_delete=models.CASCADE, related_name='inventory_requirements')
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='service_requirements')
    quantity_required = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_service_requirement'
        unique_together = [('service', 'item')]
        ordering = ['service__name', 'item__name']

    def __str__(self):
        return f'{self.service.name} needs {self.quantity_required} x {self.item.name}'
