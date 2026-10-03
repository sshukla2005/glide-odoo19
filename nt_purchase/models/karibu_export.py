from odoo import _, fields, models
from odoo.exceptions import UserError

EXPORT_STATES = [
    ('exported', "Exported"),
    ('uploaded', "Uploaded to Portal"),
    ('confirmed', "Confirmed by Supplier"),
    ('rejected', "Rejected"),
    ('superseded', "Superseded"),
]


class NtKaribuExport(models.Model):
    """One generated LPO workbook, kept so it can be downloaded again."""
    _name = 'nt.karibu.export'
    _description = 'Karibu LPO Export'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    name = fields.Char(string="LPO Reference", required=True, readonly=True, index=True)
    # restrict: the export history must survive; a purchase order that was
    # exported cannot be deleted, only cancelled.
    order_id = fields.Many2one(
        'purchase.order', string="Purchase Order", required=True,
        readonly=True, ondelete='restrict', index=True)
    partner_id = fields.Many2one(related='order_id.partner_id', store=True, string="Supplier")
    company_id = fields.Many2one(related='order_id.company_id', store=True)
    location_id = fields.Many2one('nt.karibu.location', string="Location", readonly=True)
    export_date = fields.Datetime(
        required=True, readonly=True, default=fields.Datetime.now)
    user_id = fields.Many2one(
        'res.users', string="Exported By", required=True, readonly=True,
        default=lambda self: self.env.user)
    truck_count = fields.Integer(readonly=True)
    total_tons = fields.Float(readonly=True)
    file_data = fields.Binary(string="File", readonly=True, attachment=True)
    file_name = fields.Char(readonly=True)
    state = fields.Selection(
        EXPORT_STATES, string="Status", required=True, default='exported',
        tracking=True, index=True)
    supplier_ref = fields.Char(
        string="Supplier Reference", tracking=True,
        help="Reference Tanga Cement gives the order on the Karibu Portal, "
             "for example its sales order number SOC260023661.")
    note = fields.Text()

    def action_download(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': (
                f"/web/content?model={self._name}&id={self.id}"
                f"&field=file_data&filename_field=file_name&download=true"
            ),
            'target': 'self',
        }

    def _nt_set_state(self, state, allowed_from):
        for export in self:
            if export.state not in allowed_from:
                raise UserError(_(
                    "Export %(name)s is %(state)s and cannot be changed to %(new)s.",
                    name=export.name,
                    state=dict(EXPORT_STATES)[export.state],
                    new=dict(EXPORT_STATES)[state],
                ))
        self.state = state

    def action_mark_uploaded(self):
        self._nt_set_state('uploaded', ('exported', 'rejected'))

    def action_mark_confirmed(self):
        self._nt_set_state('confirmed', ('exported', 'uploaded'))

    def action_mark_rejected(self):
        self._nt_set_state('rejected', ('exported', 'uploaded'))

    def action_reset_exported(self):
        self._nt_set_state('exported', ('uploaded', 'rejected', 'confirmed'))
