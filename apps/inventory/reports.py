"""
Export/print helpers for the Inventory module. Kept separate from
views.py purely because ReportLab table-building is verbose; the CSV
and Excel helpers here otherwise mirror the pattern already established
in apps.services.views (csv.writer / openpyxl Workbook).
"""
from apps.core.csv_utils import safe_csv_writer, safe_excel_row

from django.conf import settings
from django.http import HttpResponse

BRAND_BLUE = '#0013DE'
BRAND_PURPLE = '#0013DE'  # deprecated alias, kept for compatibility; unused


def items_csv_response(items):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="shinehub-inventory-items.csv"'
    writer = safe_csv_writer(response)
    writer.writerow(['SKU', 'Name', 'Category', 'Unit', 'Current Stock', 'Reserved', 'Available',
                      'Reorder Level', 'Avg Unit Cost', 'Stock Value', 'Status'])
    for item in items:
        writer.writerow([
            item.sku, item.name, item.category.name, item.get_unit_display(),
            item.current_stock, item.reserved_stock, item.available_stock,
            item.reorder_level, item.average_unit_cost, item.stock_value,
            'Active' if item.is_active else 'Inactive',
        ])
    return response


def items_excel_response(items):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Inventory'

    headers = ['SKU', 'Name', 'Category', 'Unit', 'Current Stock', 'Reserved', 'Available',
               'Reorder Level', 'Avg Unit Cost', 'Stock Value', 'Status']
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for item in items:
        sheet.append(safe_excel_row([
            item.sku, item.name, item.category.name, item.get_unit_display(),
            item.current_stock, item.reserved_stock, item.available_stock,
            item.reorder_level, float(item.average_unit_cost), float(item.stock_value),
            'Active' if item.is_active else 'Inactive',
        ]))

    for column_cells in sheet.columns:
        length = max((len(str(cell.value)) for cell in column_cells if cell.value is not None), default=10)
        sheet.column_dimensions[column_cells[0].column_letter].width = max(12, length + 2)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="shinehub-inventory-items.xlsx"'
    workbook.save(response)
    return response


def movements_csv_response(movements):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="shinehub-stock-movements.csv"'
    writer = safe_csv_writer(response)
    writer.writerow(['Date', 'Item', 'Movement', 'Quantity', 'Reason', 'Booking', 'Performed By'])
    for movement in movements:
        writer.writerow([
            movement.created_at.strftime('%Y-%m-%d %H:%M'),
            movement.item.name, movement.get_movement_type_display(), movement.quantity,
            movement.reason, movement.booking.booking_code if movement.booking_id else '',
            movement.performed_by.get_full_name() if movement.performed_by_id else 'System',
        ])
    return response


def _pdf_base_doc(response, title):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    doc = SimpleDocTemplate(
        response, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
        title=title,
    )
    return doc


def _pdf_header_elements(title, subtitle=''):
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, Spacer

    styles = getSampleStyleSheet()
    elements = [
        Paragraph(f'<b>{getattr(settings, "SITE_NAME", "ShineHub")}</b>', styles['Title']),
        Paragraph(getattr(settings, 'COMPANY_NAME', ''), styles['Normal']),
        Spacer(1, 10),
        Paragraph(f'<b>{title}</b>', styles['Heading2']),
    ]
    if subtitle:
        elements.append(Paragraph(subtitle, styles['Normal']))
    elements.append(Spacer(1, 12))
    return elements


def _styled_table(data, col_widths=None):
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BRAND_BLUE)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E4E7F1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F6FB')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return table


def items_pdf_response(items, valuation_total=None):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="shinehub-inventory-report.pdf"'

    doc = _pdf_base_doc(response, 'Inventory Report')
    elements = _pdf_header_elements(
        'Inventory Stock Report',
        f'Total valuation: KSh {valuation_total:,.2f}' if valuation_total is not None else '',
    )

    data = [['SKU', 'Name', 'Category', 'Stock', 'Available', 'Reorder Lvl', 'Avg Cost', 'Value']]
    for item in items:
        data.append([
            item.sku, item.name, item.category.name, str(item.current_stock),
            str(item.available_stock), str(item.reorder_level),
            f'{item.average_unit_cost:,.2f}', f'{item.stock_value:,.2f}',
        ])

    elements.append(_styled_table(data))
    doc.build(elements)
    return response


def purchase_pdf_response(purchase):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{purchase.reference_code}.pdf"'

    doc = _pdf_base_doc(response, purchase.reference_code)
    elements = _pdf_header_elements(
        f'Purchase Order {purchase.reference_code}',
        f'Supplier: {purchase.supplier.name} — Status: {purchase.get_status_display()} — Order date: {purchase.order_date}',
    )

    data = [['Item', 'Qty Ordered', 'Qty Received', 'Unit Cost', 'Line Total']]
    for line in purchase.items.select_related('item'):
        data.append([
            line.item.name, str(line.quantity_ordered), str(line.quantity_received),
            f'{line.unit_cost:,.2f}', f'{line.line_total:,.2f}',
        ])
    data.append(['', '', '', 'Total', f'{purchase.total_amount:,.2f}'])

    elements.append(_styled_table(data))
    doc.build(elements)
    return response
