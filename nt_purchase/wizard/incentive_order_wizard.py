from odoo import _, fields, models
from odoo.exceptions import UserError


class IncentiveOrderWizard(models.TransientModel):
    _name = 'incentive.order.wizard'
    _description = 'Create Incentive'

    purchase_order_id = fields.Many2one(
        'purchase.order', string="Purchase Order", required=True, readonly=True)
    currency_id = fields.Many2one(related='purchase_order_id.currency_id')
    amount = fields.Monetary(
        string="Incentive Amount", currency_field='currency_id', required=True)
    note = fields.Text(string="Notes")

    def action_create_incentive(self):
        self.ensure_one()
        order = self.purchase_order_id
        if order.state != 'purchase':
            raise UserError(_("Incentives can only be created on confirmed purchase orders."))
        if self.amount <= 0:
            raise UserError(_("Incentive amount must be greater than zero."))

        incentive = self.env['incentive.order'].create({
            'purchase_order_id': order.id,
            'amount': self.amount,
            'note': self.note,
        })
        order.message_post(body=_(
            "Incentive %(name)s created for %(amount)s %(currency)s.",
            name=incentive.name,
            amount=self.amount,
            currency=self.currency_id.name,
        ))
        return {'type': 'ir.actions.act_window_close'}
