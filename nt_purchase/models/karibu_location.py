from odoo import fields, models


class NtKaribuLocation(models.Model):
    """A Glide branch and the account code Tanga Cement holds it under."""
    _name = 'nt.karibu.location'
    _description = 'Karibu Location'
    _order = 'name'

    name = fields.Char(required=True, help="Printed as LOCATION on the LPO, for example IRINGA.")
    code = fields.Char(
        required=True,
        help="Short code used in the export file name, for example IR.")
    customer_code = fields.Char(
        required=True,
        help="Glide's account with Tanga Cement for this branch, for example C60010467.")
    signatory_name = fields.Char(
        help="Name printed above 'Authorized Signatory'.")
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        'unique (code, company_id)',
        "That location code already exists.",
    )
