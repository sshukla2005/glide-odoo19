from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.nt_stock.models.truck_mixin import TRUCK_FIELDS


class SaleOrder(models.Model):
    _inherit = ['sale.order', 'nt.truck.mixin']
    _name = 'sale.order'

    fixed_discount_amount = fields.Monetary(
        string="Fixed Discount",
        currency_field='currency_id',
        tracking=True,
        help="One fixed amount deducted from the whole order, without tax. "
             "It is added as a 'Fixed Discount' line when the quotation is saved.",
    )

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string="Purchase Order",
        tracking=True,
        copy=False,
        help="Truck details are taken from this purchase order.",
    )
    vehicle_id = fields.Many2one(
        compute='_compute_vehicle_id',
        store=True,
        readonly=False,
    )

    # ------------------------------------------------------------------
    # Truck details from the purchase order
    # ------------------------------------------------------------------
    @api.depends('purchase_order_id')
    def _compute_vehicle_id(self):
        for order in self:
            if order.purchase_order_id:
                order.vehicle_id = order.purchase_order_id.vehicle_id
            else:
                order.vehicle_id = order.vehicle_id

    @api.depends('purchase_order_id')
    def _compute_truck_details(self):
        from_po = self.filtered(
            lambda o: o.purchase_order_id
            and o.vehicle_id == o.purchase_order_id.vehicle_id
        )
        for order in from_po:
            order.driver_id = order.purchase_order_id.driver_id
            order.license_plate = order.purchase_order_id.license_plate
        return super(SaleOrder, self - from_po)._compute_truck_details()

    def _nt_locking_pickings(self):
        return self.picking_ids

    @api.depends('picking_ids.state')
    def _compute_truck_locked(self):
        return super()._compute_truck_locked()

    def _action_confirm(self):
        res = super()._action_confirm()
        for order in self:
            order._nt_sync_truck_to_pickings(order.picking_ids)
        return res

    # ------------------------------------------------------------------
    # Fixed discount
    # ------------------------------------------------------------------
    @api.constrains('fixed_discount_amount')
    def _check_fixed_discount_amount(self):
        for order in self:
            if order.fixed_discount_amount < 0:
                raise ValidationError(_("Fixed discount cannot be negative."))

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        if not self.env.context.get('nt_skip_fixed_discount'):
            orders.filtered('fixed_discount_amount')._nt_apply_fixed_discount()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if (
            not self.env.context.get('nt_skip_fixed_discount')
            and {'fixed_discount_amount', 'order_line'} & set(vals)
        ):
            self._nt_apply_fixed_discount()
        if {'purchase_order_id', *TRUCK_FIELDS} & set(vals):
            for order in self:
                order._nt_sync_truck_to_pickings(order.picking_ids)
        return res

    def _nt_apply_fixed_discount(self):
        """Replace the order's fixed-discount line with a single untaxed line
        of -fixed_discount_amount."""
        discount_product = self.env.ref('nt_sale.product_fixed_discount')
        for order in self.with_context(nt_skip_fixed_discount=True):
            if order.state not in ('draft', 'sent'):
                continue

            order.order_line.filtered('is_fixed_discount').unlink()

            product_lines = order.order_line.filtered(
                lambda l: not l.display_type and not l.is_downpayment
            )
            amount = order.fixed_discount_amount
            if not amount or not product_lines:
                continue

            lines_untaxed = sum(product_lines.mapped('price_subtotal'))
            if order.currency_id.compare_amounts(amount, lines_untaxed) > 0:
                raise ValidationError(_(
                    "Fixed discount (%(discount)s) cannot be more than the "
                    "untaxed amount of the order lines (%(untaxed)s).",
                    discount=amount,
                    untaxed=lines_untaxed,
                ))

            order.env['sale.order.line'].create({
                'order_id': order.id,
                'product_id': discount_product.id,
                'name': _("Fixed Discount"),
                'product_uom_qty': 1.0,
                'price_unit': -amount,
                'tax_ids': [Command.clear()],
                'sequence': max(order.order_line.mapped('sequence') or [0]) + 1,
                'is_fixed_discount': True,
            })
