from odoo import api, models


class StockPicking(models.Model):
    _inherit = ['stock.picking', 'nt.truck.mixin']
    _name = 'stock.picking'

    def _nt_locking_pickings(self):
        return self

    @api.depends('state')
    def _compute_truck_locked(self):
        return super()._compute_truck_locked()
