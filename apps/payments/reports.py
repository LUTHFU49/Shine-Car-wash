"""
Export/print helpers for Payments, mirroring apps.inventory.reports.
"""
from apps.core.csv_utils import safe_csv_writer, safe_excel_row
import io

from django.conf import settings
from django.http import HttpResponse

BRAND_BLUE = '#0013DE'


def transactions_csv_response(payments):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="shinehub-transactions.csv"'
    writer = safe_csv_writer(response)
    writer.writerow(['Reference', 'Date', 'Booking', 'Method', 'Amount', 'Status', 'M-Pesa Receipt', 'Initiated By'])
    for payment in payments:
        writer.writerow([
            payment.reference_code, payment.created_at.strftime('%Y-%m-%d %H:%M'),
            payment.invoice.booking.booking_code, payment.get_method_display(), payment.amount,
            payment.get_status_display(), payment.mpesa_receipt_number,
            payment.initiated_by.get_full_name() if payment.initiated_by_id else '',
        ])
    return response


def transactions_excel_response(payments):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Transactions'
    headers = ['Reference', 'Date', 'Booking', 'Method', 'Amount', 'Status', 'M-Pesa Receipt', 'Initiated By']
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for payment in payments:
        sheet.append(safe_excel_row([
            payment.reference_code, payment.created_at.strftime('%Y-%m-%d %H:%M'),
            payment.invoice.booking.booking_code, payment.get_method_display(), float(payment.amount),
            payment.get_status_display(), payment.mpesa_receipt_number,
            payment.initiated_by.get_full_name() if payment.initiated_by_id else '',
        ]))

    for column_cells in sheet.columns:
        length = max((len(str(cell.value)) for cell in column_cells if cell.value is not None), default=10)
        sheet.column_dimensions[column_cells[0].column_letter].width = max(12, length + 2)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="shinehub-transactions.xlsx"'
    workbook.save(response)
    return response


def collections_csv_response(rows):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="shinehub-daily-collections.csv"'
    writer = safe_csv_writer(response)
    writer.writerow(['Date', 'Cash', 'M-Pesa', 'Total'])
    for row in rows:
        writer.writerow([row['date'], row['cash_total'], row['mpesa_total'], row['total']])
    return response


def _pdf_base_doc(buffer_or_response, title):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    return SimpleDocTemplate(
        buffer_or_response, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
        title=title,
    )


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
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E4E7F1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F6FB')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return table


def invoice_pdf_response(invoice):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{invoice.invoice_number}.pdf"'

    doc = _pdf_base_doc(response, invoice.invoice_number)
    elements = _pdf_header_elements(
        f'Invoice {invoice.invoice_number}',
        f'Booking: {invoice.booking.booking_code} — Customer: {invoice.booking.customer.first_name} {invoice.booking.customer.last_name} — Issued: {invoice.issued_date}',
    )

    data = [['Description', 'Amount (KSh)']]
    data.append([invoice.booking.service.name, f'{invoice.subtotal:,.2f}'])
    if invoice.tax_amount:
        data.append([f'Tax ({invoice.tax_rate}%)', f'{invoice.tax_amount:,.2f}'])
    data.append(['Total', f'{invoice.total_amount:,.2f}'])
    data.append(['Amount Paid', f'{invoice.amount_paid:,.2f}'])
    data.append(['Balance Due', f'{invoice.balance:,.2f}'])

    elements.append(_styled_table(data, col_widths=[340, 120]))
    doc.build(elements)
    return response


def _payment_receipt_elements(payment):
    invoice = payment.invoice
    elements = _pdf_header_elements(
        f'Payment Receipt {payment.reference_code}',
        f'Booking: {invoice.booking.booking_code} — {payment.get_method_display()} — {payment.created_at.strftime("%B %d, %Y %H:%M")}',
    )
    data = [['Field', 'Detail']]
    data.append(['Amount Paid', f'KSh {payment.amount:,.2f}'])
    data.append(['Method', payment.get_method_display()])
    if payment.method == 'mpesa' and payment.mpesa_receipt_number:
        data.append(['M-Pesa Receipt No.', payment.mpesa_receipt_number])
    data.append(['Status', payment.get_status_display()])
    data.append(['Invoice Balance After Payment', f'KSh {invoice.balance:,.2f}'])
    elements.append(_styled_table(data, col_widths=[220, 240]))
    return elements


def payment_receipt_pdf_bytes(payment):
    """Returns raw PDF bytes -- used both for the download view and as
    an email attachment on the payment-received notification."""
    buffer = io.BytesIO()
    doc = _pdf_base_doc(buffer, payment.reference_code)
    doc.build(_payment_receipt_elements(payment))
    return buffer.getvalue()


def payment_receipt_pdf_response(payment):
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{payment.reference_code}.pdf"'
    response.write(payment_receipt_pdf_bytes(payment))
    return response
