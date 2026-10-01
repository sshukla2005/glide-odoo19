from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_fixed_discount = fields.Boolean(
        string="Fixed Discount Line",
        readonly=True,
        help="Technical flag: line generated from the order's Fixed Discount field.",
    )

    def _compute_price_unit(self):
        # Keep the discount price as set; never recompute it from the pricelist.
        fixed_lines = self.filtered('is_fixed_discount')
        return super(SaleOrderLine, self - fixed_lines)._compute_price_unit()

    def _compute_tax_ids(self):
        # The discount lines carry the taxes of the order lines they discount
        # (set by sale.order._nt_apply_fixed_discount), not the taxes of the
        # discount product.
        fixed_lines = self.filtered('is_fixed_discount')
        for line in fixed_lines:
            line.tax_ids = line.tax_ids
        return super(SaleOrderLine, self - fixed_lines)._compute_tax_ids()
