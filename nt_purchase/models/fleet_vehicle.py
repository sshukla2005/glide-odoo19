from odoo import fields, models


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    nt_trailer_no = fields.Char(
        string="Trailer Number",
        help="Trailer normally coupled to this truck. Can be overridden per LPO line.")
