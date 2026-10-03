from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    nt_karibu_product_id = fields.Many2one(
        'nt.karibu.product', string="Karibu Code",
        help="Tanga Cement's code for this product, used when exporting an LPO.")
