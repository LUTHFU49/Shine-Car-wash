import csv

# Characters that make a spreadsheet app (Excel, Sheets, LibreOffice)
# treat a CSV cell as a formula to evaluate when the file is opened --
# classic "CSV injection". None of this app's exports contain only
# trusted data (customer names, vehicle notes, item names, feedback
# text, etc. are all user-supplied), so every export needs this.
FORMULA_TRIGGER_CHARS = ('=', '+', '-', '@', '\t', '\r')


def _sanitize_csv_cell(value):
    """
    A leading single quote makes every major spreadsheet app treat the
    cell as forced plain text instead of evaluating it as a formula --
    the standard mitigation for CSV injection. Non-strings (numbers,
    dates, None) pass through unchanged since they can't carry a
    formula prefix.
    """
    if isinstance(value, str) and value.startswith(FORMULA_TRIGGER_CHARS):
        return "'" + value
    return value


class SafeCSVWriter:
    """
    Drop-in replacement for csv.writer with the same .writerow()/
    .writerows() interface, except every cell is passed through
    _sanitize_csv_cell first. Use this everywhere this app writes a
    CSV export containing any user-supplied data -- which in practice
    is every export in this app.
    """

    def __init__(self, response, **kwargs):
        self._writer = csv.writer(response, **kwargs)

    def writerow(self, row):
        return self._writer.writerow([_sanitize_csv_cell(cell) for cell in row])

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


def safe_csv_writer(response, **kwargs):
    return SafeCSVWriter(response, **kwargs)


def safe_excel_row(row):
    """
    Same formula-injection protection as SafeCSVWriter, for openpyxl
    exports: use `sheet.append(safe_excel_row([...]))` instead of
    `sheet.append([...])` for any row containing user-supplied data.
    openpyxl stores a cell value starting with '=' as a live formula
    Excel will evaluate on open, so this needs the identical mitigation.
    """
    return [_sanitize_csv_cell(cell) for cell in row]
