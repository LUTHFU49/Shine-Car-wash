"""
All stock-changing business logic lives here rather than scattered across
views/signals, so InventoryItem.current_stock / reserved_stock / 
average_unit_cost stay consistent with the StockMovement ledger no matter
which caller (a view, a signal, a management command) triggers a change.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from .models import (
    InventoryItem, ItemBatch, PurchaseStatus, ServiceInventoryRequirement,
    StockMovement, StockReservation,
)

LOW_STOCK_ALERT_COOLDOWN_HOURS = 24


# ============================================================
# Low stock alerting (in-app notification + branded email digest)
# ============================================================

def _maybe_alert_low_stock(item):
    item.refresh_from_db()
    if not item.is_low_stock:
        return

    if item.low_stock_alerted_at:
        elapsed = timezone.now() - item.low_stock_alerted_at
        if elapsed.total_seconds() < LOW_STOCK_ALERT_COOLDOWN_HOURS * 3600:
            return

    from apps.accounts.models import Role
    from apps.notifications.utils import notify_roles
    from apps.notifications.models import NotificationLevel
    from apps.accounts.emails import send_branded_email
    from apps.accounts.models import User

    detail_url = reverse('inventory:item_detail', args=[item.public_id])
    message = (
        f'{item.name} ({item.sku}) has {item.available_stock} {item.get_unit_display()} '
        f'available -- at or below the reorder level of {item.reorder_level}.'
    )
    notify_roles(
        [Role.SUPER_ADMIN, Role.MANAGER],
        title=f'Low stock: {item.name}',
        message=message,
        level=NotificationLevel.WARNING,
        url=detail_url,
    )

    managers = User.objects.filter(
        role__in=[Role.SUPER_ADMIN, Role.MANAGER], is_active=True, is_deactivated=False,
    ).exclude(email='')
    for manager in managers:
        send_branded_email(
            subject='Low stock alert',
            template_name='low_stock_alert_email.html',
            context={'user': manager, 'item': item, 'detail_url': detail_url},
            to_email=manager.email,
        )

    InventoryItem.objects.filter(pk=item.pk).update(low_stock_alerted_at=timezone.now())


# ============================================================
# Batches (expiry tracking)
# ============================================================

def _consume_batches_fifo(item, quantity):
    """Deduct `quantity` from the item's batches, oldest expiry first.
    Only meaningful for items with track_expiry=True; a no-op otherwise."""
    if not item.track_expiry:
        return

    remaining = quantity
    batches = ItemBatch.objects.filter(item=item, quantity_remaining__gt=0).order_by('expiry_date', 'received_date')
    for batch in batches:
        if remaining <= 0:
            break
        take = min(batch.quantity_remaining, remaining)
        ItemBatch.objects.filter(pk=batch.pk).update(quantity_remaining=F('quantity_remaining') - take)
        remaining -= take
    # If remaining > 0 here, batch records under-account for current_stock
    # (e.g. batches were never backfilled for older stock) -- the
    # denormalized current_stock is still authoritative for totals.


def write_off_expired_batches(user=None):
    """Meant to be run periodically (see management command
    `check_expired_stock`). Writes off any batch whose expiry_date has
    passed and still has quantity_remaining, deducting it from the
    parent item's current_stock with an EXPIRED movement."""
    today = timezone.localdate()
    expired_batches = ItemBatch.objects.filter(expiry_date__lt=today, quantity_remaining__gt=0).select_related('item')
    written_off = []
    for batch in expired_batches:
        qty = batch.quantity_remaining
        item = batch.item
        with transaction.atomic():
            InventoryItem.objects.filter(pk=item.pk).update(current_stock=F('current_stock') - qty)
            ItemBatch.objects.filter(pk=batch.pk).update(quantity_remaining=0)
            StockMovement.objects.create(
                item=item, batch=batch, movement_type=StockMovement.MovementType.EXPIRED,
                quantity=qty, unit_cost_at_time=batch.unit_cost,
                reason=f'Batch {batch.batch_number or batch.pk} expired {batch.expiry_date}.',
                performed_by=user,
            )
        _maybe_alert_low_stock(item)
        written_off.append(batch)
    return written_off


# ============================================================
# Manual stock adjustments / damage
# ============================================================

def adjust_stock(item, quantity, direction, reason, user):
    """direction is 'in' or 'out'. Used for stock counts / corrections."""
    if quantity <= 0:
        raise ValidationError('Adjustment quantity must be greater than zero.')

    with transaction.atomic():
        if direction == 'out':
            if quantity > item.available_stock:
                raise ValidationError('Cannot remove more than the available stock.')
            InventoryItem.objects.filter(pk=item.pk).update(current_stock=F('current_stock') - quantity)
            _consume_batches_fifo(item, quantity)
            movement_type = StockMovement.MovementType.ADJUSTMENT_OUT
        else:
            InventoryItem.objects.filter(pk=item.pk).update(current_stock=F('current_stock') + quantity)
            movement_type = StockMovement.MovementType.ADJUSTMENT_IN

        StockMovement.objects.create(
            item=item, movement_type=movement_type, quantity=quantity,
            reason=reason, performed_by=user,
        )

    item.refresh_from_db()
    _maybe_alert_low_stock(item)
    return item


def record_damage(item, quantity, reason, user):
    if quantity <= 0:
        raise ValidationError('Quantity must be greater than zero.')
    if quantity > item.available_stock:
        raise ValidationError('Cannot write off more than the available stock.')

    with transaction.atomic():
        InventoryItem.objects.filter(pk=item.pk).update(current_stock=F('current_stock') - quantity)
        _consume_batches_fifo(item, quantity)
        StockMovement.objects.create(
            item=item, movement_type=StockMovement.MovementType.DAMAGED,
            quantity=quantity, reason=reason, performed_by=user,
        )

    item.refresh_from_db()
    _maybe_alert_low_stock(item)
    return item


# ============================================================
# Purchases
# ============================================================

def receive_purchase(purchase, user):
    """Marks a Purchase RECEIVED and moves every line's quantity_ordered
    into stock, updating each item's weighted-average cost and, for
    expiry-tracked items, creating a dated batch."""
    if purchase.status == PurchaseStatus.RECEIVED:
        raise ValidationError('This purchase has already been received.')
    if purchase.status == PurchaseStatus.CANCELLED:
        raise ValidationError('A cancelled purchase cannot be received.')

    with transaction.atomic():
        for line in purchase.items.select_related('item').select_for_update():
            item = line.item
            qty = line.quantity_ordered
            unit_cost = line.unit_cost

            existing_value = item.current_stock * item.average_unit_cost
            incoming_value = qty * unit_cost
            new_total_qty = item.current_stock + qty
            new_avg_cost = (
                (existing_value + incoming_value) / new_total_qty
                if new_total_qty > 0 else unit_cost
            )

            InventoryItem.objects.filter(pk=item.pk).update(
                current_stock=F('current_stock') + qty,
                average_unit_cost=new_avg_cost,
            )

            batch = None
            if item.track_expiry:
                batch = ItemBatch.objects.create(
                    item=item, quantity_received=qty, quantity_remaining=qty,
                    unit_cost=unit_cost, expiry_date=line.expiry_date, purchase_item=line,
                )

            StockMovement.objects.create(
                item=item, batch=batch, movement_type=StockMovement.MovementType.PURCHASE_IN,
                quantity=qty, unit_cost_at_time=unit_cost, purchase_item=line,
                performed_by=user,
            )

            line.quantity_received = qty
            line.save(update_fields=['quantity_received'])

        purchase.status = PurchaseStatus.RECEIVED
        purchase.received_date = timezone.localdate()
        purchase.save(update_fields=['status', 'received_date', 'updated_at'])

    if purchase.created_by and purchase.created_by.email:
        from apps.accounts.emails import send_branded_email
        send_branded_email(
            subject=f'Purchase {purchase.reference_code} received',
            template_name='purchase_received_email.html',
            context={'user': purchase.created_by, 'purchase': purchase},
            to_email=purchase.created_by.email,
        )

    from apps.notifications.utils import notify
    from apps.notifications.models import NotificationLevel
    if purchase.created_by:
        notify(
            purchase.created_by,
            title=f'Purchase {purchase.reference_code} received',
            message=f'Stock from {purchase.supplier.name} has been added to inventory.',
            level=NotificationLevel.SUCCESS,
            url=reverse('inventory:purchase_detail', args=[purchase.public_id]),
        )

    return purchase


# ============================================================
# Booking integration (called from apps.inventory.signals)
# ============================================================

def reserve_stock_for_booking(booking):
    """Reserves stock for every ServiceInventoryRequirement of the
    booking's service. Idempotent: a booking's reservations are only
    ever created once, the first time it reaches CONFIRMED."""
    if StockReservation.objects.filter(booking=booking).exists():
        return

    requirements = ServiceInventoryRequirement.objects.filter(service_id=booking.service_id).select_related('item')
    if not requirements:
        return

    with transaction.atomic():
        for requirement in requirements:
            item = requirement.item
            StockReservation.objects.create(
                booking=booking, item=item, quantity=requirement.quantity_required,
            )
            InventoryItem.objects.filter(pk=item.pk).update(
                reserved_stock=F('reserved_stock') + requirement.quantity_required,
            )
            StockMovement.objects.create(
                item=item, movement_type=StockMovement.MovementType.BOOKING_RESERVED,
                quantity=requirement.quantity_required, booking=booking,
            )

    for requirement in requirements:
        _maybe_alert_low_stock(requirement.item)


def consume_reserved_stock(booking):
    """Called when a booking is COMPLETED: turns its active reservations
    into a real deduction from stock. Idempotent against re-saves."""
    already_consumed = StockMovement.objects.filter(
        booking=booking, movement_type=StockMovement.MovementType.BOOKING_USED,
    ).exists()
    if already_consumed:
        return

    reservations = StockReservation.objects.filter(
        booking=booking, status=StockReservation.ReservationStatus.ACTIVE,
    ).select_related('item')

    for reservation in reservations:
        item = reservation.item
        qty = reservation.quantity
        with transaction.atomic():
            InventoryItem.objects.filter(pk=item.pk).update(
                current_stock=F('current_stock') - qty,
                reserved_stock=F('reserved_stock') - qty,
            )
            _consume_batches_fifo(item, qty)
            StockMovement.objects.create(
                item=item, movement_type=StockMovement.MovementType.BOOKING_USED,
                quantity=qty, booking=booking, unit_cost_at_time=item.average_unit_cost,
            )
            reservation.status = StockReservation.ReservationStatus.CONSUMED
            reservation.save(update_fields=['status', 'updated_at'])

        _maybe_alert_low_stock(item)


def release_reservations_for_booking(booking):
    """Called when a booking is CANCELLED or marked NO_SHOW: releases any
    still-active reservations back to available stock."""
    reservations = StockReservation.objects.filter(
        booking=booking, status=StockReservation.ReservationStatus.ACTIVE,
    ).select_related('item')

    for reservation in reservations:
        with transaction.atomic():
            InventoryItem.objects.filter(pk=reservation.item_id).update(
                reserved_stock=F('reserved_stock') - reservation.quantity,
            )
            StockMovement.objects.create(
                item=reservation.item, movement_type=StockMovement.MovementType.BOOKING_RELEASED,
                quantity=reservation.quantity, booking=booking,
            )
            reservation.status = StockReservation.ReservationStatus.RELEASED
            reservation.save(update_fields=['status', 'updated_at'])


# ============================================================
# Valuation
# ============================================================

def compute_total_valuation():
    from django.db.models import ExpressionWrapper, DecimalField, Sum
    result = InventoryItem.objects.filter(is_active=True).aggregate(
        total=Sum(
            ExpressionWrapper(F('current_stock') * F('average_unit_cost'), output_field=DecimalField(max_digits=14, decimal_places=2)),
        ),
    )
    return result['total'] or Decimal('0.00')
