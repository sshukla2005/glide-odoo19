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
        help="One fixed amount deducted from the untaxed total of the order. "
             "VAT is computed on the amount after this discount. It is added "
             "as 'Fixed Discount' line(s) when the quotation is saved.",
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

    def _recompute_taxes(self):
        # "Update Taxes" (fiscal position change) recomputes line taxes;
        # rebuild the discount so it follows the new taxes.
        res = super()._recompute_taxes()
        self._nt_apply_fixed_discount()
        return res

    def _recompute_prices(self):
        # "Update Prices" changes the subtotals the discount is split on.
        res = super()._recompute_prices()
        self._nt_apply_fixed_discount()
        return res

    def _nt_apply_fixed_discount(self):
        """Replace the order's fixed-discount lines.

        The fixed amount is tax-excluded: it reduces the untaxed amount by
        exactly fixed_discount_amount, and VAT is then computed on the
        discounted amount (as on the client's TRA invoices). The amount is
        split over the tax groups of the order lines in proportion to their
        untaxed subtotals, one discount line per tax group, each carrying
        that group's taxes. Fixed-amount taxes (e.g. excise per ton) are
        not applied to the discount.
        """
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

            currency = order.currency_id
            lines_untaxed = sum(product_lines.mapped('price_subtotal'))
            if currency.compare_amounts(amount, lines_untaxed) > 0:
                raise ValidationError(_(
                    "Fixed discount (%(discount)s) cannot be more than the "
                    "untaxed amount of the order lines (%(untaxed)s).",
                    discount=amount,
                    untaxed=lines_untaxed,
                ))

            sequence = max(order.order_line.mapped('sequence') or [0]) + 1
            split = order._nt_split_fixed_discount(product_lines, amount)
            vals_list = []
            for taxes, share in split:
                if len(split) == 1:
                    name = _("Fixed Discount")
                else:
                    name = _(
                        "Fixed Discount (%(taxes)s)",
                        taxes=", ".join(taxes.mapped('name')) or _("No Tax"),
                    )
                vals_list.append({
                    'order_id': order.id,
                    'product_id': discount_product.id,
                    'name': name,
                    'product_uom_qty': 1.0,
                    'price_unit': -order._nt_discount_price_unit(taxes, share),
                    'tax_ids': [Command.set(taxes.ids)],
                    'sequence': sequence,
                    'is_fixed_discount': True,
                })
            order.env['sale.order.line'].create(vals_list)

    def _nt_split_fixed_discount(self, product_lines, amount):
        """Return [(taxes, share)] splitting `amount` over the tax groups of
        `product_lines` in proportion to their untaxed subtotals. The shares
        always add up to exactly `amount`."""
        self.ensure_one()
        currency = self.currency_id
        weights = {}
        for line in product_lines:
            taxes = line.tax_ids.filtered(lambda t: t.amount_type != 'fixed')
            key = tuple(sorted(taxes.ids))
            weights[key] = weights.get(key, 0.0) + line.price_subtotal
        groups = sorted(
            ((key, weight) for key, weight in weights.items()
             if not currency.is_zero(weight)),
            key=lambda kw: kw[1],
            reverse=True,
        )
        if not groups:
            return [(self.env['account.tax'], amount)]

        total = sum(weight for _key, weight in groups)
        result = []
        allocated = 0.0
        # Smaller groups get a rounded share; the largest group takes the
        # remainder so the total discount is exact.
        for key, weight in groups[1:]:
            share = currency.round(amount * weight / total)
            allocated += share
            result.append((self.env['account.tax'].browse(key), share))
        result.insert(0, (
            self.env['account.tax'].browse(groups[0][0]),
            currency.round(amount - allocated),
        ))
        return [(taxes, share) for taxes, share in result
                if not currency.is_zero(share)]

    def _nt_discount_price_unit(self, taxes, untaxed_amount):
        """Unit price that gives a line subtotal of `untaxed_amount`.
        Only differs from `untaxed_amount` when a tax is price-included."""
        self.ensure_one()
        if not taxes or not any(taxes.mapped('price_include')):
            return untaxed_amount
        # Gross/net ratio measured on a large amount so rounding is negligible.
        probe = 1e9
        excluded = taxes.compute_all(
            probe,
            currency=self.currency_id,
            quantity=1.0,
            product=self.env.ref('nt_sale.product_fixed_discount'),
            partner=self.partner_id,
        )['total_excluded']
        if not excluded:
            return untaxed_amount
        return self.currency_id.round(untaxed_amount * probe / excluded)
