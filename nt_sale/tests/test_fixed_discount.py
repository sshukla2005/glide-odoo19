from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.sale.tests.common import SaleCommon


@tagged('post_install', '-at_install')
class TestFixedDiscount(SaleCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vat18 = cls.env['account.tax'].create({
            'name': 'VAT 18%',
            'amount_type': 'percent',
            'amount': 18.0,
            'type_tax_use': 'sale',
            'company_id': cls.env.company.id,
        })
        cls.vat_exempt = cls.env['account.tax'].create({
            'name': 'VAT Exempt',
            'amount_type': 'percent',
            'amount': 0.0,
            'type_tax_use': 'sale',
            'company_id': cls.env.company.id,
        })
        cls.cement = cls.env['product.product'].create({
            'name': 'Simba Cement Bags 50Kgs - 32.5R grade + Transport',
            'type': 'consu',
            'list_price': 322257.28,
            'taxes_id': [Command.set(cls.vat18.ids)],
        })
        cls.exempt_product = cls.env['product.product'].create({
            'name': 'Exempt Item',
            'type': 'service',
            'list_price': 1000.0,
            'taxes_id': [Command.set(cls.vat_exempt.ids)],
        })

    def _set_price_precision(self, digits):
        # Glide's invoices use rates with more than 2 decimals
        # (16425: 9,989,975.83 / 31 t = 322,257.2848).
        self.env.ref('product.decimal_price').digits = digits

    def _order(self, lines, discount=0.0):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'fixed_discount_amount': discount,
            'order_line': [
                Command.create({
                    'product_id': product.id,
                    'product_uom_qty': qty,
                    'price_unit': price,
                    'tax_ids': [Command.set(taxes.ids)],
                })
                for product, qty, price, taxes in lines
            ],
        })

    def _discount_lines(self, order):
        return order.order_line.filtered('is_fixed_discount')

    def test_invoice_16425(self):
        """Reproduce Glide invoice 16425: VAT is charged after the discount."""
        self._set_price_precision(4)
        order = self._order(
            [(self.cement, 31, 322257.2848, self.vat18)], discount=1583196.17)
        disc = self._discount_lines(order)
        self.assertEqual(len(disc), 1)
        self.assertEqual(disc.tax_ids, self.vat18)
        self.assertAlmostEqual(disc.price_subtotal, -1583196.17, places=2)
        self.assertAlmostEqual(order.amount_untaxed, 8406779.66, places=2)
        self.assertAlmostEqual(order.amount_tax, 1513220.34, places=2)
        self.assertAlmostEqual(order.amount_total, 9920000.00, places=2)

    def test_invoice_carries_same_amounts(self):
        self._set_price_precision(4)
        order = self._order(
            [(self.cement, 31, 322257.2848, self.vat18)], discount=1583196.17)
        order.action_confirm()
        # Invoice everything (cement is consu; deliver first for policy).
        order.order_line.filtered(lambda l: not l.is_fixed_discount).qty_delivered = 31
        invoice = order._create_invoices()
        disc = invoice.invoice_line_ids.filtered(lambda l: l.price_subtotal < 0)
        self.assertEqual(disc.tax_ids, self.vat18)
        self.assertAlmostEqual(invoice.amount_untaxed, 8406779.66, places=2)
        self.assertAlmostEqual(invoice.amount_tax, 1513220.34, places=2)
        self.assertAlmostEqual(invoice.amount_total, 9920000.00, places=2)

    def test_split_over_tax_groups(self):
        order = self._order([
            (self.cement, 1, 3000.0, self.vat18),
            (self.exempt_product, 1, 1000.0, self.vat_exempt),
        ], discount=100.0)
        disc = self._discount_lines(order)
        self.assertEqual(len(disc), 2)
        self.assertAlmostEqual(sum(disc.mapped('price_subtotal')), -100.0, places=2)
        vat_line = disc.filtered(lambda l: l.tax_ids == self.vat18)
        exempt_line = disc.filtered(lambda l: l.tax_ids == self.vat_exempt)
        self.assertAlmostEqual(vat_line.price_subtotal, -75.0, places=2)
        self.assertAlmostEqual(exempt_line.price_subtotal, -25.0, places=2)
        self.assertAlmostEqual(order.amount_untaxed, 3900.0, places=2)
        self.assertAlmostEqual(order.amount_tax, 2925.0 * 0.18, places=2)

    def test_split_rounding_is_exact(self):
        order = self._order([
            (self.cement, 1, 100.0, self.vat18),
            (self.exempt_product, 1, 200.0, self.vat_exempt),
        ], discount=100.0)
        self.assertAlmostEqual(
            sum(self._discount_lines(order).mapped('price_subtotal')), -100.0, places=2)
        self.assertAlmostEqual(order.amount_untaxed, 200.0, places=2)

    def test_price_included_tax(self):
        vat_incl = self.vat18.copy({'name': 'VAT 18% incl', 'price_include_override': 'tax_included'})
        order = self._order([(self.cement, 1, 1180.0, vat_incl)], discount=100.0)
        disc = self._discount_lines(order)
        self.assertAlmostEqual(disc.price_subtotal, -100.0, places=2)
        self.assertAlmostEqual(order.amount_untaxed, 900.0, places=2)
        self.assertAlmostEqual(order.amount_tax, 162.0, places=2)

    def test_fixed_tax_not_applied_to_discount(self):
        excise = self.env['account.tax'].create({
            'name': 'Excise 20,000/ton',
            'amount_type': 'fixed',
            'amount': 20000.0,
            'type_tax_use': 'sale',
            'include_base_amount': True,
            'sequence': 1,
            'company_id': self.env.company.id,
        })
        order = self._order(
            [(self.cement, 31, 242237.29, excise | self.vat18)], discount=1000.0)
        disc = self._discount_lines(order)
        self.assertEqual(disc.tax_ids, self.vat18)
        self.assertAlmostEqual(disc.price_tax, -180.0, places=2)

    def test_rebuilt_on_change_and_removed(self):
        order = self._order([(self.cement, 31, 322257.28, self.vat18)], discount=1000.0)
        order.fixed_discount_amount = 2000.0
        disc = self._discount_lines(order)
        self.assertEqual(len(disc), 1)
        self.assertAlmostEqual(disc.price_subtotal, -2000.0, places=2)
        order.fixed_discount_amount = 0.0
        self.assertFalse(self._discount_lines(order))

    def test_taxes_kept_on_recompute(self):
        order = self._order([(self.cement, 31, 322257.28, self.vat18)], discount=1000.0)
        disc = self._discount_lines(order)
        disc._compute_tax_ids()
        self.assertEqual(disc.tax_ids, self.vat18)
        order._recompute_taxes()
        self.assertEqual(self._discount_lines(order).tax_ids, self.vat18)

    def test_discount_cannot_exceed_untaxed(self):
        with self.assertRaises(ValidationError):
            self._order([(self.cement, 1, 100.0, self.vat18)], discount=101.0)
