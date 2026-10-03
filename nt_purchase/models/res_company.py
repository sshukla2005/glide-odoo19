from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    nt_tin = fields.Char(
        string="TIN",
        help="Taxpayer Identification Number printed on the LPO letterhead.")
