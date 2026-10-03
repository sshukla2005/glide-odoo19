from odoo import api, fields, models


class NtKaribuProduct(models.Model):
    """Tanga Cement's own product codes, as published in the Karibu template."""
    _name = 'nt.karibu.product'
    _description = 'Karibu Cement Code'
    _order = 'sequence, code'
    _rec_name = 'code'

    sequence = fields.Integer(default=10)
    code = fields.Char(
        string="Karibu Code", required=True,
        help="Code the Karibu Portal expects, for example BAG425N.")
    description = fields.Char(
        required=True,
        help="Full description, written to the Products sheet of the export.")
    short_type = fields.Char(
        string="Product Type",
        help="Short grade printed on the LPO, for example 42.5N;50KG.")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        'unique (code)',
        "That Karibu code already exists.",
    )

    @api.depends('code', 'description')
    def _compute_display_name(self):
        for record in self:
            parts = [p for p in (record.code, record.description) if p]
            record.display_name = " — ".join(parts)
