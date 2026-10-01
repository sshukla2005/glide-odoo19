from odoo import _, api, fields, models

from odoo.addons.nt_stock.models.truck_mixin import TRUCK_FIELDS


class PurchaseOrder(models.Model):
    _inherit = ['purchase.order', 'nt.truck.mixin']
    _name = 'purchase.order'

    incentive_order_ids = fields.One2many(
        'incentive.order', 'purchase_order_id', string="Incentives")
    incentive_count = fields.Integer(compute='_compute_incentive_count')

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
