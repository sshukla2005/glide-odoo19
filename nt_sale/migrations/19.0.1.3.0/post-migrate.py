import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Rebuild the fixed-discount lines of open quotations so they carry VAT.

    Before 19.0.1.3.0 the discount line was untaxed, which charged VAT on the
    gross amount. Confirmed orders are left untouched.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env['sale.order'].search([
        ('state', 'in', ('draft', 'sent')),
        ('fixed_discount_amount', '>', 0),
    ])
    for order in orders:
        try:
            with cr.savepoint():
                order._nt_apply_fixed_discount()
        except Exception:
            _logger.exception("nt_sale: could not rebuild fixed discount on %s", order.name)
    _logger.info("nt_sale: rebuilt fixed discount on %s quotation(s)", len(orders))
