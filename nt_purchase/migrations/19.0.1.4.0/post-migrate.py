from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Exports made before 19.0.1.4.0 have no status: keep the latest one per
    order as 'exported' and mark the earlier ones superseded."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env['nt.karibu.export'].search([]).order_id
    for order in orders:
        exports = order.nt_karibu_export_ids.sorted(
            lambda e: (e.create_date, e.id), reverse=True)
        exports[1:].filtered(lambda e: e.state == 'exported').state = 'superseded'
