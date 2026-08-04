import csv
import io
import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit_logs.models import AuditLog
from apps.core.decorators import management_required, staff_required

from . import services
from .forms import (
    CSVImportForm, DamageReportForm, InventoryCategoryForm, InventoryItemForm,
    ItemSearchForm, PurchaseForm, PurchaseItemFormSet, ServiceInventoryRequirementForm,
    StockAdjustmentForm, SupplierForm,
)
from .models import (
    InventoryCategory, InventoryItem, ItemBatch, Purchase, PurchaseStatus,
    ServiceInventoryRequirement, StockMovement, Supplier,
)
from .reports import (
    items_csv_response, items_excel_response, items_pdf_response,
    movements_csv_response, purchase_pdf_response,
)

PAGE_SIZE = 20


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _log(request, action, model_name, obj, description):
    AuditLog.objects.create(
        user=request.user, action=action, model_name=model_name,
        object_id=str(obj.pk), description=description,
        ip_address=_client_ip(request),
    )


# ============================================================
# Dashboard
# ============================================================

@staff_required
def dashboard_view(request):
    items = InventoryItem.objects.filter(is_active=True).select_related('category')
    low_stock_items = [item for item in items if item.is_low_stock]
    expiring_batches = (
        ItemBatch.objects.filter(quantity_remaining__gt=0, expiry_date__isnull=False)
        .filter(expiry_date__lte=timezone.localdate() + timezone.timedelta(days=14))
        .select_related('item').order_by('expiry_date')[:10]
    )
    recent_movements = StockMovement.objects.select_related('item', 'booking').order_by('-created_at')[:10]
    pending_purchases = Purchase.objects.filter(status__in=[PurchaseStatus.DRAFT, PurchaseStatus.ORDERED]).count()

    by_category = (
        InventoryCategory.objects.filter(is_active=True)
        .annotate(item_count=Count('items', filter=Q(items__is_active=True)))
        .order_by('-item_count')[:8]
    )

    return render(request, 'inventory/dashboard.html', {
        'total_items': items.count(),
        'low_stock_items': low_stock_items,
        'low_stock_count': len(low_stock_items),
        'expiring_batches': expiring_batches,
        'recent_movements': recent_movements,
        'pending_purchases': pending_purchases,
        'valuation_total': services.compute_total_valuation(),
        'category_chart_labels': json.dumps([c.name for c in by_category]),
        'category_chart_values': json.dumps([c.item_count for c in by_category]),
    })


# ============================================================
# Categories
# ============================================================

@staff_required
def category_list_view(request):
    categories = InventoryCategory.objects.annotate(item_count=Count('items')).order_by('display_order', 'name')
    return render(request, 'inventory/category_list.html', {'categories': categories})


@management_required
def category_create_view(request):
    if request.method == 'POST':
        form = InventoryCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = request.user
            category.save()
            _log(request, AuditLog.Action.CREATE, 'InventoryCategory', category, f'Created category "{category.name}"')
            messages.success(request, f'{category.name} has been added.')
            return redirect('inventory:category_list')
    else:
        form = InventoryCategoryForm()
    return render(request, 'inventory/category_form.html', {'form': form, 'is_create': True})


@management_required
def category_edit_view(request, public_id):
    category = get_object_or_404(InventoryCategory, public_id=public_id)
    if request.method == 'POST':
        form = InventoryCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            _log(request, AuditLog.Action.UPDATE, 'InventoryCategory', category, f'Updated category "{category.name}"')
            messages.success(request, 'Category updated.')
            return redirect('inventory:category_list')
    else:
        form = InventoryCategoryForm(instance=category)
    return render(request, 'inventory/category_form.html', {'form': form, 'is_create': False, 'category': category})


@management_required
@require_POST
def category_set_status_view(request, public_id, new_status):
    category = get_object_or_404(InventoryCategory, public_id=public_id)
    category.is_active = new_status == 'active'
    category.save(update_fields=['is_active'])
    _log(request, AuditLog.Action.UPDATE, 'InventoryCategory', category, f'Status set to {new_status} for "{category.name}"')
    messages.success(request, f'{category.name} marked as {"active" if category.is_active else "inactive"}.')
    return redirect('inventory:category_list')


# ============================================================
# Suppliers
# ============================================================

@staff_required
def supplier_list_view(request):
    suppliers = Supplier.objects.annotate(purchase_count=Count('purchases')).order_by('name')
    return render(request, 'inventory/supplier_list.html', {'suppliers': suppliers})


@management_required
def supplier_create_view(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.created_by = request.user
            supplier.save()
            _log(request, AuditLog.Action.CREATE, 'Supplier', supplier, f'Created supplier "{supplier.name}"')
            messages.success(request, f'{supplier.name} has been added.')
            return redirect('inventory:supplier_list')
    else:
        form = SupplierForm()
    return render(request, 'inventory/supplier_form.html', {'form': form, 'is_create': True})


@management_required
def supplier_edit_view(request, public_id):
    supplier = get_object_or_404(Supplier, public_id=public_id)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            _log(request, AuditLog.Action.UPDATE, 'Supplier', supplier, f'Updated supplier "{supplier.name}"')
            messages.success(request, 'Supplier updated.')
            return redirect('inventory:supplier_list')
    else:
        form = SupplierForm(instance=supplier)
    return render(request, 'inventory/supplier_form.html', {'form': form, 'is_create': False, 'supplier': supplier})


@management_required
@require_POST
def supplier_set_status_view(request, public_id, new_status):
    supplier = get_object_or_404(Supplier, public_id=public_id)
    supplier.is_active = new_status == 'active'
    supplier.save(update_fields=['is_active'])
    _log(request, AuditLog.Action.UPDATE, 'Supplier', supplier, f'Status set to {new_status} for "{supplier.name}"')
    messages.success(request, f'{supplier.name} marked as {"active" if supplier.is_active else "inactive"}.')
    return redirect('inventory:supplier_list')


# ============================================================
# Items
# ============================================================

def _filtered_items_queryset(request):
    queryset = InventoryItem.objects.select_related('category').all()
    search_form = ItemSearchForm(request.GET)

    if search_form.is_valid():
        q = search_form.cleaned_data.get('q')
        if q:
            queryset = queryset.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(description__icontains=q))

        category = search_form.cleaned_data.get('category')
        if category:
            queryset = queryset.filter(category=category)

        status = search_form.cleaned_data.get('status')
        if status:
            queryset = queryset.filter(is_active=(status == 'active'))

        stock_state = search_form.cleaned_data.get('stock_state')
        if stock_state == 'out':
            queryset = queryset.filter(current_stock__lte=0)

    items = list(queryset.order_by('name'))
    if search_form.is_valid() and search_form.cleaned_data.get('stock_state') == 'low':
        items = [item for item in items if item.is_low_stock]

    return items, search_form


@staff_required
def item_list_view(request):
    items, search_form = _filtered_items_queryset(request)
    paginator = Paginator(items, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))

    querystring = request.GET.copy()
    querystring.pop('page', None)

    return render(request, 'inventory/item_list.html', {
        'search_form': search_form,
        'page_obj': page_obj,
        'total_count': len(items),
        'querystring': querystring.urlencode(),
    })


@management_required
def item_create_view(request):
    if not InventoryCategory.objects.filter(is_active=True).exists():
        messages.error(request, 'Create an inventory category first.')
        return redirect('inventory:category_create')

    if request.method == 'POST':
        form = InventoryItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            item.created_by = request.user
            item.save()
            _log(request, AuditLog.Action.CREATE, 'InventoryItem', item, f'Created item "{item.name}" ({item.sku})')
            messages.success(request, f'{item.name} has been added to inventory.')
            return redirect('inventory:item_detail', public_id=item.public_id)
    else:
        form = InventoryItemForm()
    return render(request, 'inventory/item_form.html', {'form': form, 'is_create': True})


@staff_required
def item_detail_view(request, public_id):
    item = get_object_or_404(InventoryItem.objects.select_related('category'), public_id=public_id)
    movements = item.movements.select_related('booking', 'performed_by').order_by('-created_at')[:50]
    batches = item.batches.filter(quantity_remaining__gt=0).order_by('expiry_date') if item.track_expiry else []
    requirements = item.service_requirements.select_related('service')

    adjustment_form = StockAdjustmentForm()
    damage_form = DamageReportForm()

    return render(request, 'inventory/item_detail.html', {
        'item': item, 'movements': movements, 'batches': batches,
        'requirements': requirements, 'adjustment_form': adjustment_form,
        'damage_form': damage_form,
    })


@management_required
def item_edit_view(request, public_id):
    item = get_object_or_404(InventoryItem, public_id=public_id)
    if request.method == 'POST':
        form = InventoryItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            _log(request, AuditLog.Action.UPDATE, 'InventoryItem', item, f'Updated item "{item.name}"')
            messages.success(request, 'Item updated.')
            return redirect('inventory:item_detail', public_id=item.public_id)
    else:
        form = InventoryItemForm(instance=item)
    return render(request, 'inventory/item_form.html', {'form': form, 'is_create': False, 'item': item})


@management_required
@require_POST
def item_set_status_view(request, public_id, new_status):
    item = get_object_or_404(InventoryItem, public_id=public_id)
    item.is_active = new_status == 'active'
    item.save(update_fields=['is_active'])
    _log(request, AuditLog.Action.UPDATE, 'InventoryItem', item, f'Status set to {new_status} for "{item.name}"')
    messages.success(request, f'{item.name} marked as {"active" if item.is_active else "inactive"}.')
    return redirect('inventory:item_detail', public_id=item.public_id)


@management_required
@require_POST
def item_bulk_action_view(request):
    action = request.POST.get('action')
    public_ids = request.POST.getlist('selected')
    items = InventoryItem.objects.filter(public_id__in=public_ids)

    if not items.exists():
        messages.warning(request, 'No items were selected.')
        return redirect('inventory:item_list')

    if action == 'activate':
        items.update(is_active=True)
        messages.success(request, f'{items.count()} item(s) marked as active.')
    elif action == 'deactivate':
        items.update(is_active=False)
        messages.success(request, f'{items.count()} item(s) marked as inactive.')
    elif action == 'set_category':
        category_id = request.POST.get('category')
        category = get_object_or_404(InventoryCategory, public_id=category_id)
        items.update(category=category)
        messages.success(request, f'{items.count()} item(s) moved to "{category.name}".')
    else:
        messages.error(request, 'Unknown bulk action.')
        return redirect('inventory:item_list')

    AuditLog.objects.create(
        user=request.user, action=AuditLog.Action.UPDATE, model_name='InventoryItem',
        description=f'Bulk action "{action}" applied to {len(public_ids)} item(s)',
        ip_address=_client_ip(request),
    )
    return redirect('inventory:item_list')


@management_required
@require_POST
def item_adjust_stock_view(request, public_id):
    item = get_object_or_404(InventoryItem, public_id=public_id)
    form = StockAdjustmentForm(request.POST)
    if form.is_valid():
        try:
            services.adjust_stock(
                item, form.cleaned_data['quantity'], form.cleaned_data['direction'],
                form.cleaned_data['reason'], request.user,
            )
            _log(request, AuditLog.Action.UPDATE, 'InventoryItem', item,
                 f'Stock {form.cleaned_data["direction"]} adjustment of {form.cleaned_data["quantity"]} for "{item.name}"')
            messages.success(request, 'Stock adjustment recorded.')
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
    else:
        messages.error(request, 'Please correct the errors in the adjustment form.')
    return redirect('inventory:item_detail', public_id=item.public_id)


@management_required
@require_POST
def item_report_damage_view(request, public_id):
    item = get_object_or_404(InventoryItem, public_id=public_id)
    form = DamageReportForm(request.POST)
    if form.is_valid():
        try:
            services.record_damage(item, form.cleaned_data['quantity'], form.cleaned_data['reason'], request.user)
            _log(request, AuditLog.Action.UPDATE, 'InventoryItem', item,
                 f'Damaged stock of {form.cleaned_data["quantity"]} recorded for "{item.name}"')
            messages.success(request, 'Damaged stock recorded and deducted.')
        except ValidationError as exc:
            messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
    else:
        messages.error(request, 'Please correct the errors in the damage report form.')
    return redirect('inventory:item_detail', public_id=item.public_id)


@management_required
def item_csv_import_view(request):
    if request.method == 'POST':
        form = CSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            decoded = form.cleaned_data['csv_file'].read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(decoded))
            created, skipped = 0, 0
            for row in reader:
                name = (row.get('name') or '').strip()
                category_name = (row.get('category') or '').strip()
                if not name or not category_name:
                    skipped += 1
                    continue
                category, _ = InventoryCategory.objects.get_or_create(
                    name=category_name, defaults={'created_by': request.user},
                )
                unit = (row.get('unit') or 'piece').strip().lower()
                reorder_level = row.get('reorder_level') or 5
                track_expiry = (row.get('track_expiry') or 'no').strip().lower() in {'yes', 'true', '1'}

                if InventoryItem.objects.filter(name__iexact=name, category=category).exists():
                    skipped += 1
                    continue

                InventoryItem.objects.create(
                    category=category, name=name, unit=unit if unit else 'piece',
                    reorder_level=reorder_level, track_expiry=track_expiry, created_by=request.user,
                )
                created += 1

            _log(request, AuditLog.Action.CREATE, 'InventoryItem', request.user,
                 f'CSV import: {created} created, {skipped} skipped')
            messages.success(request, f'Import complete: {created} item(s) created, {skipped} skipped.')
            return redirect('inventory:item_list')
    else:
        form = CSVImportForm()
    return render(request, 'inventory/item_csv_import.html', {'form': form})


@staff_required
def item_export_csv_view(request):
    items, _ = _filtered_items_queryset(request)
    return items_csv_response(items)


@staff_required
def item_export_excel_view(request):
    items, _ = _filtered_items_queryset(request)
    return items_excel_response(items)


@staff_required
def item_export_pdf_view(request):
    items, _ = _filtered_items_queryset(request)
    return items_pdf_response(items, valuation_total=services.compute_total_valuation())


@staff_required
def item_print_report_view(request):
    items, _ = _filtered_items_queryset(request)
    return render(request, 'inventory/print_report.html', {
        'items': items, 'valuation_total': services.compute_total_valuation(),
        'generated_at': timezone.localtime(),
    })


# ============================================================
# Stock movement ledger
# ============================================================

@staff_required
def movement_list_view(request):
    movements = StockMovement.objects.select_related('item', 'booking', 'performed_by').order_by('-created_at')

    item_id = request.GET.get('item')
    if item_id:
        movements = movements.filter(item__public_id=item_id)

    movement_type = request.GET.get('type')
    if movement_type in StockMovement.MovementType.values:
        movements = movements.filter(movement_type=movement_type)

    paginator = Paginator(movements, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'inventory/movement_list.html', {'page_obj': page_obj})


@staff_required
def movement_export_csv_view(request):
    movements = StockMovement.objects.select_related('item', 'booking', 'performed_by').order_by('-created_at')
    return movements_csv_response(movements)


# ============================================================
# Purchases
# ============================================================

@staff_required
def purchase_list_view(request):
    purchases = Purchase.objects.select_related('supplier').order_by('-created_at')
    status = request.GET.get('status')
    if status in PurchaseStatus.values:
        purchases = purchases.filter(status=status)

    paginator = Paginator(purchases, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'inventory/purchase_list.html', {'page_obj': page_obj})


@management_required
def purchase_create_view(request):
    if not Supplier.objects.filter(is_active=True).exists():
        messages.error(request, 'Add a supplier first.')
        return redirect('inventory:supplier_create')

    if request.method == 'POST':
        form = PurchaseForm(request.POST)
        formset = PurchaseItemFormSet(request.POST, instance=Purchase())
        if form.is_valid() and formset.is_valid():
            purchase = form.save(commit=False)
            purchase.created_by = request.user
            purchase.status = PurchaseStatus.ORDERED
            purchase.save()
            formset.instance = purchase
            formset.save()
            _log(request, AuditLog.Action.CREATE, 'Purchase', purchase, f'Created purchase order {purchase.reference_code}')
            messages.success(request, f'Purchase order {purchase.reference_code} created.')
            return redirect('inventory:purchase_detail', public_id=purchase.public_id)
    else:
        form = PurchaseForm()
        formset = PurchaseItemFormSet(instance=Purchase())

    return render(request, 'inventory/purchase_form.html', {'form': form, 'formset': formset, 'is_create': True})


@staff_required
def purchase_detail_view(request, public_id):
    purchase = get_object_or_404(Purchase.objects.select_related('supplier'), public_id=public_id)
    lines = purchase.items.select_related('item')
    return render(request, 'inventory/purchase_detail.html', {'purchase': purchase, 'lines': lines})


@management_required
def purchase_edit_view(request, public_id):
    purchase = get_object_or_404(Purchase, public_id=public_id)
    if not purchase.is_editable:
        messages.error(request, 'Only draft or ordered purchases can be edited.')
        return redirect('inventory:purchase_detail', public_id=purchase.public_id)

    if request.method == 'POST':
        form = PurchaseForm(request.POST, instance=purchase)
        formset = PurchaseItemFormSet(request.POST, instance=purchase)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            _log(request, AuditLog.Action.UPDATE, 'Purchase', purchase, f'Updated purchase order {purchase.reference_code}')
            messages.success(request, 'Purchase order updated.')
            return redirect('inventory:purchase_detail', public_id=purchase.public_id)
    else:
        form = PurchaseForm(instance=purchase)
        formset = PurchaseItemFormSet(instance=purchase)

    return render(request, 'inventory/purchase_form.html', {'form': form, 'formset': formset, 'is_create': False, 'purchase': purchase})


@management_required
@require_POST
def purchase_receive_view(request, public_id):
    purchase = get_object_or_404(Purchase, public_id=public_id)
    try:
        services.receive_purchase(purchase, request.user)
        _log(request, AuditLog.Action.UPDATE, 'Purchase', purchase, f'Received purchase order {purchase.reference_code}')
        messages.success(request, f'{purchase.reference_code} received -- stock levels updated.')
    except ValidationError as exc:
        messages.error(request, exc.message if hasattr(exc, 'message') else str(exc))
    return redirect('inventory:purchase_detail', public_id=purchase.public_id)


@management_required
@require_POST
def purchase_cancel_view(request, public_id):
    purchase = get_object_or_404(Purchase, public_id=public_id)
    if purchase.status == PurchaseStatus.RECEIVED:
        messages.error(request, 'A received purchase cannot be cancelled.')
    else:
        purchase.status = PurchaseStatus.CANCELLED
        purchase.save(update_fields=['status', 'updated_at'])
        _log(request, AuditLog.Action.UPDATE, 'Purchase', purchase, f'Cancelled purchase order {purchase.reference_code}')
        messages.success(request, f'{purchase.reference_code} cancelled.')
    return redirect('inventory:purchase_detail', public_id=purchase.public_id)


@staff_required
def purchase_export_pdf_view(request, public_id):
    purchase = get_object_or_404(Purchase.objects.select_related('supplier'), public_id=public_id)
    return purchase_pdf_response(purchase)


# ============================================================
# Service <-> Inventory requirements
# ============================================================

@staff_required
def requirement_list_view(request):
    requirements = ServiceInventoryRequirement.objects.select_related('service', 'item').order_by('service__name')
    return render(request, 'inventory/requirement_list.html', {'requirements': requirements})


@management_required
def requirement_create_view(request):
    if request.method == 'POST':
        form = ServiceInventoryRequirementForm(request.POST)
        if form.is_valid():
            requirement = form.save()
            _log(request, AuditLog.Action.CREATE, 'ServiceInventoryRequirement', requirement,
                 f'Linked "{requirement.item.name}" to service "{requirement.service.name}"')
            messages.success(request, 'Requirement saved.')
            return redirect('inventory:requirement_list')
    else:
        form = ServiceInventoryRequirementForm()
    return render(request, 'inventory/requirement_form.html', {'form': form})


@management_required
@require_POST
def requirement_delete_view(request, pk):
    requirement = get_object_or_404(ServiceInventoryRequirement, pk=pk)
    description = f'Removed link between "{requirement.item.name}" and "{requirement.service.name}"'
    requirement.delete()
    AuditLog.objects.create(
        user=request.user, action=AuditLog.Action.DELETE, model_name='ServiceInventoryRequirement',
        description=description, ip_address=_client_ip(request),
    )
    messages.success(request, 'Requirement removed.')
    return redirect('inventory:requirement_list')
