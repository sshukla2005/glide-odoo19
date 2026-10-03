import base64
import io
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.nt_stock.models.truck_mixin import TRUCK_FIELDS
from odoo.addons.nt_purchase.tools.karibu_workbook import build_karibu_workbook


class PurchaseOrder(models.Model):
    _inherit = ['purchase.order', 'nt.truck.mixin']
    _name = 'purchase.order'

    incentive_order_ids = fields.One2many(
        'incentive.order', 'purchase_order_id', string="Incentives")
    incentive_count = fields.Integer(compute='_compute_incentive_count')

    # ------------------------------------------------------------------
    # Karibu Portal LPO
    # ------------------------------------------------------------------
    nt_is_karibu = fields.Boolean(
        string="Karibu LPO", compute='_compute_nt_is_karibu', store=True, readonly=False,
        help="Show the Karibu LPO tab and allow exporting the supplier workbook.")
    nt_lpo_ref = fields.Char(
        string="LPO Reference", copy=False, tracking=True,
        help="Reference Tanga Cement assigns to this order, for example GPAL-12292.")
    nt_lpo_date = fields.Date(
        string="LPO Date", copy=False, default=fields.Date.context_today)
    nt_karibu_location_id = fields.Many2one(
        'nt.karibu.location', string="Karibu Location",
        domain="[('company_id', '=', company_id)]")
    nt_karibu_line_ids = fields.One2many(
        'nt.karibu.truck.line', 'order_id', string="Trucks", copy=True)
    nt_karibu_total_tons = fields.Float(
        string="Total MT", compute='_compute_nt_karibu_total_tons', store=True)
    nt_karibu_export_ids = fields.One2many(
        'nt.karibu.export', 'order_id', string="Karibu Exports")
    nt_karibu_export_count = fields.Integer(compute='_compute_nt_karibu_export_count')

    @api.depends('partner_id.nt_is_karibu_supplier')
    def _compute_nt_is_karibu(self):
        for order in self:
            order.nt_is_karibu = order.partner_id.nt_is_karibu_supplier

    @api.depends('nt_karibu_line_ids.qty_tons')
    def _compute_nt_karibu_total_tons(self):
        for order in self:
            order.nt_karibu_total_tons = sum(order.nt_karibu_line_ids.mapped('qty_tons'))

    @api.depends('nt_karibu_export_ids')
    def _compute_nt_karibu_export_count(self):
        for order in self:
            order.nt_karibu_export_count = len(order.nt_karibu_export_ids)

    def _nt_karibu_check(self):
        """Raise if anything the supplier's template requires is missing."""
        self.ensure_one()
        problems = []
        if self.state == 'cancel':
            problems.append(_("the order is cancelled"))
        if not self.nt_lpo_ref:
            problems.append(_("the LPO reference is empty"))
        if not self.nt_karibu_location_id:
            problems.append(_("no Karibu location is set"))
        if not self.nt_karibu_line_ids:
            problems.append(_("no trucks have been added"))
        for index, line in enumerate(self.nt_karibu_line_ids, start=1):
            if not line.karibu_product_id:
                problems.append(_("truck %s has no cement code", index))
            if not line.truck_no:
                problems.append(_("truck %s has no registration number", index))
            if not line.license_no:
                problems.append(
                    _("truck %(n)s: driver %(d)s has no licence number",
                      n=index, d=line.driver_id.display_name or ""))
        if problems:
            raise UserError(_(
                "This order cannot be exported yet:\n\n- %s",
                "\n- ".join(problems)))

    def _nt_karibu_company_address(self):
        company = self.company_id
        parts = [company.street, company.street2, company.city, company.zip]
        parts = [p for p in parts if p]
        if company.country_id:
            parts.append(company.country_id.name)
        return ", ".join(parts)

    def _nt_karibu_payload(self):
        self.ensure_one()
        company = self.company_id
        supplier = self.partner_id
        location = self.nt_karibu_location_id
        return {
            'reference': self.nt_lpo_ref,
            'date': self.nt_lpo_date,
            'location': location.name,
            'customer_code': location.customer_code,
            'signatory': location.signatory_name or "",
            'company': {
                'name': company.name,
                'address': self._nt_karibu_company_address(),
                'phone': company.phone or "",
                'email': company.email or "",
                'tin': company.nt_tin or "",
                'vrn': company.vat or "",
            },
            'supplier': {
                'name': supplier.name,
                'street': supplier.street or "",
                'street2': ", ".join(
                    p for p in (supplier.street2, supplier.city,
                                supplier.country_id.name) if p),
                'phone': f"Tel: {supplier.phone}" if supplier.phone else "",
                'email': supplier.email or "",
            },
            'lines': [{
                'driver': line.driver_id.display_name or "",
                'license': line.license_no or "",
                'truck': line.truck_no or "",
                'trailer': line.trailer_no or "",
                'qty': line.qty_tons,
                'product_code': line.karibu_product_id.code,
                'product_type': line.product_type or "",
                'transporter': line.transporter or "",
            } for line in self.nt_karibu_line_ids],
        }

    def _nt_karibu_file_name(self):
        """GPAL-12292 at location IR becomes GPAL_IR_-_12292.xlsx."""
        self.ensure_one()
        reference = (self.nt_lpo_ref or "").strip()
        code = self.nt_karibu_location_id.code or ""
        match = re.match(r'^([A-Za-z]+)[-_ ]*(.+)$', reference)
        if match:
            return f"{match.group(1)}_{code}_-_{match.group(2)}.xlsx"
        return f"{re.sub(r'[^A-Za-z0-9._-]+', '_', reference) or 'KARIBU_LPO'}.xlsx"

    def action_karibu_export(self):
        self.ensure_one()
        self._nt_karibu_check()

        products = self.env['nt.karibu.product'].search([])
        if not products:
            raise UserError(_(
                "No Karibu cement codes are configured. Add them under "
                "Purchase > Configuration > Karibu Cement Codes."))

        workbook = build_karibu_workbook(
            self._nt_karibu_payload(),
            [{
                'code': product.code,
                'description': product.description,
                'short_type': product.short_type,
            } for product in products],
        )
        stream = io.BytesIO()
        workbook.save(stream)

        export = self.env['nt.karibu.export'].create({
            'name': self.nt_lpo_ref,
            'order_id': self.id,
            'location_id': self.nt_karibu_location_id.id,
            'truck_count': len(self.nt_karibu_line_ids),
            'total_tons': self.nt_karibu_total_tons,
            'file_data': base64.b64encode(stream.getvalue()),
            'file_name': self._nt_karibu_file_name(),
        })
        self.message_post(body=_(
            "Karibu LPO %(ref)s exported — %(trucks)s truck(s), %(tons)s MT.",
            ref=self.nt_lpo_ref,
            trucks=len(self.nt_karibu_line_ids),
            tons=self.nt_karibu_total_tons,
        ))
        return export.action_download()

    def action_view_karibu_exports(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'nt_purchase.action_karibu_export')
        action['domain'] = [('order_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    @api.depends('incentive_order_ids')
    def _compute_incentive_count(self):
        for order in self:
            order.incentive_count = len(order.incentive_order_ids)

    # ------------------------------------------------------------------
    # Truck details -> receipts
    # ------------------------------------------------------------------
    def _nt_locking_pickings(self):
        return self.picking_ids

    @api.depends('picking_ids.state')
    def _compute_truck_locked(self):
        return super()._compute_truck_locked()

    def _create_picking(self):
        res = super()._create_picking()
        for order in self:
            order._nt_sync_truck_to_pickings(order.picking_ids)
        return res

    def write(self, vals):
        res = super().write(vals)
        if set(TRUCK_FIELDS) & set(vals):
            for order in self:
                order._nt_sync_truck_to_pickings(order.picking_ids)
        return res

    # ------------------------------------------------------------------
    # Incentives
    # ------------------------------------------------------------------
    def action_open_incentive_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Create Incentive"),
            'res_model': 'incentive.order.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_purchase_order_id': self.id},
        }

    def action_view_incentive_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'nt_purchase.action_incentive_order')
        action['domain'] = [('purchase_order_id', '=', self.id)]
        action['context'] = {'create': False}
        if self.incentive_count == 1:
            action.update({
                'view_mode': 'form',
                'views': [(False, 'form')],
                'res_id': self.incentive_order_ids.id,
            })
        return action
