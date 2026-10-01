from odoo import _, api, fields, models
from odoo.exceptions import UserError

TRUCK_FIELDS = ('vehicle_id', 'driver_id', 'license_plate')


class NtTruckMixin(models.AbstractModel):
    """Truck details shared by purchase orders, sale orders and transfers."""
    _name = 'nt.truck.mixin'
    _description = 'Truck Details'

    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string="Truck",
        tracking=True,
        copy=True,
    )
    driver_id = fields.Many2one(
        'res.partner',
        string="Driver",
        compute='_compute_truck_details',
        store=True,
        readonly=False,
        copy=True,
        tracking=True,
    )
    license_plate = fields.Char(
        string="License Plate",
        compute='_compute_truck_details',
        store=True,
        readonly=False,
        copy=True,
        tracking=True,
    )
    driver_phone = fields.Char(related='driver_id.phone', string="Driver Phone")
    truck_locked = fields.Boolean(
        string="Truck Details Locked",
        compute='_compute_truck_locked',
        help="Truck details can no longer be changed because the receipt "
             "or delivery is already done.",
    )

    @api.depends('vehicle_id')
    def _compute_truck_details(self):
        for record in self:
            record.driver_id = record.vehicle_id.driver_id
            record.license_plate = record.vehicle_id.license_plate

    def _nt_locking_pickings(self):
        """Transfers whose 'done' state freezes the truck details."""
        return self.env['stock.picking']

    def _compute_truck_locked(self):
        for record in self:
            record.truck_locked = any(
                picking.state == 'done' for picking in record._nt_locking_pickings()
            )

    def write(self, vals):
        if set(TRUCK_FIELDS) & set(vals):
            locked = self.filtered('truck_locked')
            if locked:
                raise UserError(_(
                    "Truck details cannot be changed once the receipt or delivery "
                    "is done: %s",
                    ", ".join(locked.mapped('display_name')),
                ))
        return super().write(vals)

    def _nt_truck_vals(self):
        self.ensure_one()
        return {
            'vehicle_id': self.vehicle_id.id,
            'driver_id': self.driver_id.id,
            'license_plate': self.license_plate,
        }

    def _nt_sync_truck_to_pickings(self, pickings):
        """Copy this record's truck details to transfers that are not done/cancelled."""
        self.ensure_one()
        open_pickings = pickings.filtered(lambda p: p.state not in ('done', 'cancel'))
        if open_pickings:
            open_pickings.write(self._nt_truck_vals())
