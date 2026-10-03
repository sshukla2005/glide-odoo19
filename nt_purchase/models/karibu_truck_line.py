from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class NtKaribuTruckLine(models.Model):
    """One truck on an LPO: one row on the BulkUpload sheet and one on the
    printed order."""
    _name = 'nt.karibu.truck.line'
    _description = 'Karibu LPO Truck Line'
    _order = 'order_id, sequence, id'

    order_id = fields.Many2one(
        'purchase.order', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True)
    sequence = fields.Integer(default=10)

    # Each autofilled field has its own compute: fields sharing one compute
    # are protected together, so passing one of them on create would leave
    # the others empty. precompute fills them before the INSERT, which the
    # NOT NULL on driver_id needs outside the form view (imports, scripts).
    vehicle_id = fields.Many2one(
        'fleet.vehicle', string="Truck", required=True,
        help="Truck collecting this load.")
    truck_no = fields.Char(
        string="Truck Reg.", compute='_compute_truck_no',
        store=True, readonly=False, precompute=True, copy=True)
    trailer_no = fields.Char(
        string="Trailer", compute='_compute_trailer_no',
        store=True, readonly=False, precompute=True, copy=True)
    driver_id = fields.Many2one(
        'res.partner', string="Driver", compute='_compute_driver_id',
        store=True, readonly=False, precompute=True, copy=True, required=True)
    license_no = fields.Char(
        string="Licence No.", compute='_compute_license_no',
        store=True, readonly=False, precompute=True, copy=True)

    karibu_product_id = fields.Many2one(
        'nt.karibu.product', string="Cement Code", required=True,
        compute='_compute_karibu_product_id',
        store=True, readonly=False, precompute=True, copy=True,
        help="Defaults to the Karibu code of the cement on the order lines.")
    product_type = fields.Char(
        string="Product Type", compute='_compute_product_type',
        store=True, readonly=False, precompute=True, copy=True)
    qty_tons = fields.Float(string="Qty (MT)", required=True, default=31.0)
    transporter = fields.Char(
        default=lambda self: self.env.company.name,
        help="Printed in the Transporter column. Glide's own name for own-truck "
             "loads, otherwise the hired transporter.")

    @api.depends('vehicle_id')
    def _compute_truck_no(self):
        for line in self:
            line.truck_no = line.vehicle_id.license_plate or line.truck_no

    @api.depends('vehicle_id')
    def _compute_trailer_no(self):
        for line in self:
            line.trailer_no = line.vehicle_id.nt_trailer_no or line.trailer_no

    @api.depends('vehicle_id')
    def _compute_driver_id(self):
        for line in self:
            line.driver_id = line.vehicle_id.driver_id or line.driver_id

    @api.depends('driver_id')
    def _compute_license_no(self):
        for line in self:
            line.license_no = line.driver_id.nt_license_no or line.license_no

    @api.depends('order_id')
    def _compute_karibu_product_id(self):
        for line in self:
            if line.karibu_product_id:
                line.karibu_product_id = line.karibu_product_id
                continue
            codes = line.order_id.order_line.product_id.product_tmpl_id.nt_karibu_product_id
            # Only guess when the order carries a single cement code.
            line.karibu_product_id = codes if len(codes) == 1 else False

    @api.depends('karibu_product_id')
    def _compute_product_type(self):
        for line in self:
            line.product_type = line.karibu_product_id.short_type or line.product_type

    @api.constrains('qty_tons')
    def _check_qty_tons(self):
        for line in self:
            if line.qty_tons <= 0:
                raise ValidationError(_("Tonnage must be greater than zero."))
