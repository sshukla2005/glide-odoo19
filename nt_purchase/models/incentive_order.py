from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class IncentiveOrder(models.Model):
    _name = 'incentive.order'
    _description = 'Incentive Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New'),
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string="Purchase Order",
        required=True,
        readonly=True,
        index=True,
        ondelete='restrict',
        tracking=True,
    )
    partner_id = fields.Many2one(
        related='purchase_order_id.partner_id', store=True, string="Vendor")
    company_id = fields.Many2one(
        related='purchase_order_id.company_id', store=True, string="Company")
    currency_id = fields.Many2one(
        related='purchase_order_id.currency_id', store=True, string="Currency")
    amount = fields.Monetary(
        string="Incentive Amount",
        currency_field='currency_id',
        required=True,
        tracking=True,
    )
    date = fields.Date(
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string="Created By",
        readonly=True,
        default=lambda self: self.env.user,
    )
    note = fields.Text(string="Notes")

    @api.constrains('amount')
    def _check_amount(self):
        for incentive in self:
            if incentive.amount <= 0:
                raise ValidationError(_("Incentive amount must be greater than zero."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('incentive.order') or _('New')
        return super().create(vals_list)
