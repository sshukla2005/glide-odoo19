from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    nt_license_no = fields.Char(
        string="Driving Licence No.",
        help="Printed on the Karibu LPO and sent in the bulk upload.")


class ResPartnerKaribu(models.Model):
    _inherit = 'res.partner'

    nt_is_karibu_supplier = fields.Boolean(
        string="Karibu Portal Supplier",
        help="Tick on Tanga Cement so purchase orders for this vendor show the "
             "Karibu LPO tab.")
