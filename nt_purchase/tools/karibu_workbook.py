"""Builds the Karibu Portal LPO workbook.

Reproduces the three-sheet layout supplied by the client
(GPAL_IR_-_12292.xlsx):

  Products    - TCPLC cement codes, the lookup source for the dropdown
  BulkUpload  - the rows the Karibu Portal ingests (header row 5, data 6..106)
  Sheet1      - the printable LPO on Glide letterhead

The caller passes plain dictionaries so this module stays free of Odoo
imports and can be unit tested on its own.
"""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

# Layout constants taken from the client's file.
BULK_HEADER_ROW = 5
BULK_FIRST_ROW = 6
BULK_LAST_ROW = 106                     # dropdown is defined over D6:D106
SHEET1_TABLE_HEADER_ROW = 18
SHEET1_FIRST_ROW = 19
SHEET1_MIN_ROWS = 21                    # rows 19..39 in the original
TYPE_LIST_FIRST_ROW = 12                # hidden column S holds the type list

_THIN = Side(style="thin")
_BOX = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _licence(value):
    """The portal's sample stores licence numbers as numbers, not text."""
    text = (value or "").strip()
    return int(text) if text.isdigit() else (text or None)


def _set_widths(ws, widths):
    for col, width in widths.items():
        ws.column_dimensions[col].width = width


def build_karibu_workbook(lpo, products):
    """Return an openpyxl Workbook for one LPO.

    lpo: {
        'reference', 'date' (date), 'location', 'customer_code',
        'company': {'name','street','city','country','phone','email','tin','vrn'},
        'supplier': {'name','street','street2','city','phone','email'},
        'signatory',
        'lines': [{'driver','license','truck','trailer','qty','product_code',
                   'product_type','transporter'}, ...],
    }
    products: [{'code','description','short_type'}, ...] - the full TCPLC list
    """
    wb = Workbook()
    _build_products(wb, products)
    _build_bulk_upload(wb, lpo)
    _build_sheet1(wb, lpo, products)
    wb.active = 0
    return wb


# ---------------------------------------------------------------- Products
def _build_products(wb, products):
    ws = wb.active
    ws.title = "Products"
    for offset, product in enumerate(products):
        row = 2 + offset
        ws.cell(row=row, column=1, value=product["code"])
        ws.cell(row=row, column=2, value=product["description"])
    _set_widths(ws, {"A": 9.125, "B": 39.125, "C": 8.625, "E": 43.125, "F": 8.625})

    # Named range so the BulkUpload dropdown survives as a plain validation.
    last = 1 + max(len(products), 1)
    wb.defined_names.add(
        DefinedName("KaribuProductCodes", attr_text=f"Products!$A$2:$A${last}")
    )


# ------------------------------------------------------------- BulkUpload
def _build_bulk_upload(wb, lpo):
    ws = wb.create_sheet("BulkUpload")
    headers = [
        "No",
        "Order reference no.",
        "Product",
        "Product Name",
        "Truck Reg no.",
        "Driver Licence no.",
        "Qnty (tons)",
    ]
    for col, label in enumerate(headers, start=1):
        cell = ws.cell(row=BULK_HEADER_ROW, column=col, value=label)
        cell.font = Font(bold=True)
        cell.border = _BOX
        cell.fill = PatternFill("solid", fgColor="D9D9D9")

    lines = lpo.get("lines", [])
    for index in range(BULK_FIRST_ROW, BULK_LAST_ROW + 1):
        ws.cell(row=index, column=1, value=index - BULK_FIRST_ROW + 1)
        # Column C mirrors the client's formula: the description is looked up
        # from the code the user picks in column D.
        ws.cell(
            row=index,
            column=3,
            value=f'=IF(TRIM(D{index})="","",VLOOKUP(D{index},Products!A:B,2,FALSE))',
        )

    for offset, line in enumerate(lines):
        row = BULK_FIRST_ROW + offset
        if row > BULK_LAST_ROW:
            break
        ws.cell(row=row, column=2, value=lpo["reference"])
        ws.cell(row=row, column=4, value=line["product_code"])
        ws.cell(row=row, column=5, value=line["truck"])
        ws.cell(row=row, column=6, value=_licence(line["license"]))
        ws.cell(row=row, column=7, value=line["qty"])

    validation = DataValidation(
        type="list", formula1="=KaribuProductCodes", allow_blank=True, showDropDown=False
    )
    validation.error = "Pick a cement code from the Products sheet."
    validation.errorTitle = "Unknown product code"
    ws.add_data_validation(validation)
    validation.add(f"D{BULK_FIRST_ROW}:D{BULK_LAST_ROW}")

    _set_widths(ws, {
        "A": 15.625, "B": 20.625, "C": 35.625, "D": 18.125,
        "E": 13.875, "F": 14.375, "G": 10.375, "H": 8.625,
    })


# ----------------------------------------------------------------- Sheet1
def _build_sheet1(wb, lpo, products):
    ws = wb.create_sheet("Sheet1")
    company = lpo["company"]
    supplier = lpo["supplier"]
    lines = lpo.get("lines", [])

    centre = Alignment(horizontal="center", vertical="center")

    # Letterhead
    ws["C4"] = company["name"]
    ws["C4"].font = Font(bold=True, size=14)
    ws["C4"].alignment = centre
    ws["C6"] = company.get("address", "")
    ws["C7"] = f"MOB: {company.get('phone', '')}"
    ws["C8"] = f"Email: {company.get('email', '')}"
    ws["C9"] = f"TIN: {company.get('tin', '')} | VRN: {company.get('vrn', '')}"
    for ref in ("C4", "C5", "C6", "C7", "C8", "C9"):
        ws.merge_cells(f"{ref}:J{ref[1:]}")
        ws[ref].alignment = centre

    ws["F10"] = "LOCATION"
    ws["F10"].font = Font(bold=True)
    ws["G10"] = lpo.get("location", "")

    ws["C11"] = "To"
    ws["F11"] = "CUSTOMER"
    ws["F11"].font = Font(bold=True)
    ws["G11"] = lpo.get("customer_code", "")

    ws["C12"] = supplier["name"]
    ws["C12"].font = Font(bold=True)
    ws["C13"] = supplier.get("street", "")
    ws["C14"] = supplier.get("street2", "")
    ws["C15"] = supplier.get("phone", "")
    ws["C16"] = supplier.get("email", "")

    ws["H12"] = "LPO Ref #"
    ws["H12"].font = Font(bold=True)
    ws["I12"] = lpo["reference"]
    ws.merge_cells("I12:J12")
    ws["H13"] = "LPO Date"
    ws["H13"].font = Font(bold=True)
    ws["I13"] = lpo.get("date")
    ws["I13"].number_format = "[$-1C09]dd\\ mmmm\\ yyyy;@"
    ws.merge_cells("I13:J13")

    # Hidden column S carries the product-type list the dropdown reads.
    short_types = []
    for product in products:
        value = product.get("short_type")
        if value and value not in short_types:
            short_types.append(value)
    for offset, value in enumerate(short_types):
        ws.cell(row=TYPE_LIST_FIRST_ROW + offset, column=19, value=value)
    ws.column_dimensions["S"].hidden = True

    # Truck table
    headers = [
        "S.No.", "Name of the Driver", "Driver's License #", "Truck #",
        "Trailer #", "Qty in\nMTs", "Product type", "Transporter",
    ]
    for offset, label in enumerate(headers):
        cell = ws.cell(row=SHEET1_TABLE_HEADER_ROW, column=3 + offset, value=label)
        cell.font = Font(bold=True)
        cell.border = _BOX
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.fill = PatternFill("solid", fgColor="D9D9D9")

    row_count = max(len(lines), SHEET1_MIN_ROWS)
    last_row = SHEET1_FIRST_ROW + row_count - 1
    for offset in range(row_count):
        row = SHEET1_FIRST_ROW + offset
        line = lines[offset] if offset < len(lines) else None
        values = [
            offset + 1,
            line["driver"] if line else None,
            _licence(line["license"]) if line else None,
            line["truck"] if line else None,
            line["trailer"] if line else None,
            line["qty"] if line else None,
            line["product_type"] if line else None,
            line["transporter"] if line else None,
        ]
        for col_offset, value in enumerate(values):
            cell = ws.cell(row=row, column=3 + col_offset, value=value)
            cell.border = _BOX
            if col_offset in (0, 5):
                cell.alignment = centre

    # Total row. The client's file summed the Trailer # text column and only
    # eight of the truck rows; both are corrected here.
    total_row = last_row + 1
    label = ws.cell(row=total_row, column=4, value="GRAND TOTAL:::")
    label.font = Font(bold=True)
    label.alignment = Alignment(horizontal="right")
    total = ws.cell(
        row=total_row, column=8,
        value=f"=SUM(H{SHEET1_FIRST_ROW}:H{last_row})",
    )
    total.font = Font(bold=True)
    total.border = _BOX
    total.alignment = centre

    type_validation = DataValidation(
        type="list",
        formula1=f"=$S${TYPE_LIST_FIRST_ROW}:$S${TYPE_LIST_FIRST_ROW + max(len(short_types), 1) - 1}",
        allow_blank=True,
    )
    ws.add_data_validation(type_validation)
    type_validation.add(f"I{SHEET1_FIRST_ROW}:I{last_row}")

    # Signature block, two rows clear of the total.
    sign_row = total_row + 2
    ws.cell(row=sign_row, column=8, value=f"for {company['name']}").font = Font(bold=True)
    ws.merge_cells(start_row=sign_row, start_column=8, end_row=sign_row, end_column=10)
    ws.cell(row=sign_row + 3, column=8, value=lpo.get("signatory", "")).font = Font(bold=True)
    ws.merge_cells(start_row=sign_row + 3, start_column=8, end_row=sign_row + 3, end_column=10)
    ws.cell(row=sign_row + 6, column=8, value="Authorized Signatory")
    ws.merge_cells(start_row=sign_row + 6, start_column=8, end_row=sign_row + 6, end_column=10)

    _set_widths(ws, {
        "A": 2.125, "B": 1.375, "C": 5.875, "D": 30.875, "E": 20.625,
        "F": 17.125, "G": 20.125, "H": 10.375, "I": 19.125, "J": 32.625,
        "K": 10.625, "L": 2.125, "N": 10.625, "O": 12.625, "Q": 11.125,
    })
    ws.sheet_view.showGridLines = False
