from odoo import fields, models


class NtKaribuExport(models.Model):
    """One generated LPO workbook, kept so it can be downloaded again."""
    _name = 'nt.karibu.export'
    _description = 'Karibu LPO Export'
    _order = 'create_date desc, id desc'

    name = fields.Char(string="LPO Reference", required=True, readonly=True, index=True)
    order_id = fields.Many2one(
        'purchase.order', string="Purchase Order", required=True,
        readonly=True, ondelete='cascade', index=True)
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
