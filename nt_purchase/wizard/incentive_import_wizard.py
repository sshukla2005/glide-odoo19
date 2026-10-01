import base64
import io
from datetime import date, datetime

from odoo import _, fields, models
from odoo.exceptions import UserError

# Accepted column headers (lower-cased) -> internal key
HEADER_ALIASES = {
    'po': 'po',
    'po name': 'po',
    'po number': 'po',
    'po reference': 'po',
    'purchase order': 'po',
    'amount': 'amount',
    'incentive': 'amount',
    'incentive amount': 'amount',
    'date': 'date',
    'incentive date': 'date',
    'note': 'note',
    'notes': 'note',
    'remark': 'note',
    'remarks': 'note',
}
MAX_REPORTED_ERRORS = 20


class IncentiveImportWizard(models.TransientModel):
    _name = 'incentive.import.wizard'
    _description = 'Import Incentives from Excel'

    file_data = fields.Binary(string="Excel File", required=True)
    file_name = fields.Char(string="File Name")
    default_date = fields.Date(
        string="Default Date",
        required=True,
        default=fields.Date.context_today,
        help="Used for rows that have no date column or an empty date cell.",
    )

    def _load_rows(self):
        """Return (header_map, rows) read from the uploaded workbook."""
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise UserError(_("The openpyxl library is required to import Excel files."))

        try:
            workbook = load_workbook(
                io.BytesIO(base64.b64decode(self.file_data)), data_only=True, read_only=True)
        except Exception:
            raise UserError(_("The uploaded file could not be read. Please upload a .xlsx file."))

        sheet = workbook.worksheets[0]
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            raise UserError(_("The uploaded file is empty."))

        header_map = {}
        header_index = None
        for index, row in enumerate(rows):
            candidate = {}
            for column, value in enumerate(row):
                if isinstance(value, str):
                    key = HEADER_ALIASES.get(value.strip().lower())
                    if key and key not in candidate:
                        candidate[key] = column
            if 'po' in candidate and 'amount' in candidate:
                header_map = candidate
                header_index = index
                break

        if header_index is None:
            raise UserError(_(
                "No header row found. The sheet needs a column for the purchase order "
                "(\"PO Reference\") and one for the amount (\"Incentive Amount\")."
            ))
        return header_map, rows[header_index + 1:], header_index + 2

    def _parse_date(self, value):
        if not value:
            return self.default_date
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return fields.Date.to_date(str(value).strip())

    def action_import(self):
        self.ensure_one()
        header_map, rows, first_row_number = self._load_rows()
        Purchase = self.env['purchase.order']

        errors = []
        to_create = []
        for offset, row in enumerate(rows):
            row_number = first_row_number + offset
            if not any(cell not in (None, '') for cell in row):
                continue

            po_name = row[header_map['po']]
            po_name = str(po_name).strip() if po_name not in (None, '') else ''
            raw_amount = row[header_map['amount']]
            raw_date = row[header_map['date']] if 'date' in header_map else None
            note = row[header_map['note']] if 'note' in header_map else None

            if not po_name:
                errors.append(_("Row %s: purchase order reference is empty.", row_number))
                continue

            order = Purchase.search([('name', '=', po_name)], limit=1)
            if not order:
                errors.append(_("Row %(row)s: purchase order %(po)s was not found.",
                                row=row_number, po=po_name))
                continue
            if order.state != 'purchase':
                errors.append(_("Row %(row)s: purchase order %(po)s is not confirmed.",
                                row=row_number, po=po_name))
                continue

            try:
                amount = float(str(raw_amount).replace(',', '').strip())
            except (TypeError, ValueError):
                errors.append(_("Row %(row)s: %(amount)s is not a valid amount.",
                                row=row_number, amount=raw_amount))
                continue
            if amount <= 0:
                errors.append(_("Row %s: the amount must be greater than zero.", row_number))
                continue

            try:
                incentive_date = self._parse_date(raw_date)
            except (ValueError, TypeError):
                errors.append(_("Row %(row)s: %(date)s is not a valid date.",
                                row=row_number, date=raw_date))
                continue

            to_create.append({
                'purchase_order_id': order.id,
                'amount': amount,
                'date': incentive_date,
                'note': str(note).strip() if note not in (None, '') else False,
            })

        if errors:
            shown = errors[:MAX_REPORTED_ERRORS]
            message = _("Nothing was imported. Please fix these rows:\n\n%s",
                        "\n".join(shown))
            if len(errors) > MAX_REPORTED_ERRORS:
                message += _("\n\n...and %s more.", len(errors) - MAX_REPORTED_ERRORS)
            raise UserError(message)

        if not to_create:
            raise UserError(_("No incentive rows were found in the file."))

        incentives = self.env['incentive.order'].create(to_create)
        for incentive in incentives:
            incentive.purchase_order_id.message_post(body=_(
                "Incentive %(name)s imported for %(amount)s.",
                name=incentive.name,
                amount=incentive.amount,
            ))

        action = self.env['ir.actions.act_window']._for_xml_id(
            'nt_purchase.action_incentive_order')
        action['domain'] = [('id', 'in', incentives.ids)]
        action['context'] = {'create': False}
        return action
