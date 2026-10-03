import base64
import io

from openpyxl import load_workbook

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestKaribuExport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tcplc = cls.env['res.partner'].create({
            'name': 'Tanga Cement Public Limited Company',
            'nt_is_karibu_supplier': True,
        })
        cls.driver = cls.env['res.partner'].create({
            'name': 'RAMADHANI MOSHI', 'nt_license_no': '4000539401'})
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Scania'})
        model = cls.env['fleet.vehicle.model'].create({'name': 'R460', 'brand_id': brand.id})
        cls.truck = cls.env['fleet.vehicle'].create({
            'model_id': model.id, 'license_plate': 'T740EHQ',
            'driver_id': cls.driver.id, 'nt_trailer_no': 'T123ABC'})
        cls.truck_no_driver = cls.env['fleet.vehicle'].create({
            'model_id': model.id, 'license_plate': 'T275EQX'})
        cls.code = cls.env.ref('nt_purchase.karibu_product_bag325r')
        cls.location = cls.env.ref('nt_purchase.karibu_location_iringa')
        cls.location.company_id = cls.env.company
        cls.cement = cls.env['product.product'].create({
            'name': 'Simba Imara 32.5R', 'type': 'consu',
            'uom_id': cls.env.ref('uom.product_uom_ton').id,
            'nt_karibu_product_id': cls.code.id,
        })

    def _order(self, qty=31.0, ref='GPAL-10872-01', trucks=None, confirm=True):
        order = self.env['purchase.order'].create({
            'partner_id': self.tcplc.id,
            'nt_lpo_ref': ref,
            'nt_karibu_location_id': self.location.id,
            'order_line': [Command.create({
                'product_id': self.cement.id, 'product_qty': qty, 'price_unit': 242237.29})],
        })
        order.nt_karibu_line_ids = [
            Command.create(vals) for vals in (trucks or [{'vehicle_id': self.truck.id}])]
        if confirm:
            order.button_confirm()
        return order

    # -- truck lines ----------------------------------------------------
    def test_line_autofill_from_code(self):
        """Lines created outside the form are filled from the truck, driver
        and order before insert (no NOT NULL error on driver_id)."""
        line = self._order(confirm=False).nt_karibu_line_ids
        self.assertEqual(line.truck_no, 'T740EHQ')
        self.assertEqual(line.trailer_no, 'T123ABC')
        self.assertEqual(line.driver_id, self.driver)
        self.assertEqual(line.license_no, '4000539401')
        self.assertEqual(line.karibu_product_id, self.code)
        self.assertEqual(line.product_type, '32.5R;50KG')

    def test_line_explicit_driver_keeps_other_autofill(self):
        other = self.env['res.partner'].create({'name': 'HUSSEIN MNYANI', 'nt_license_no': 'X9'})
        line = self._order(confirm=False, trucks=[
            {'vehicle_id': self.truck.id, 'driver_id': other.id}]).nt_karibu_line_ids
        self.assertEqual(line.driver_id, other)
        self.assertEqual(line.license_no, 'X9')
        self.assertEqual(line.truck_no, 'T740EHQ')
        self.assertEqual(line.trailer_no, 'T123ABC')

    def test_order_copy_keeps_manual_values(self):
        order = self._order(confirm=False, trucks=[
            {'vehicle_id': self.truck.id, 'trailer_no': 'T999ZZZ'}])
        order.nt_lpo_ref = False
        copy = order.copy()
        self.assertEqual(copy.nt_karibu_line_ids.trailer_no, 'T999ZZZ')
        self.assertEqual(copy.nt_karibu_line_ids.driver_id, self.driver)

    # -- export checks --------------------------------------------------
    def test_draft_order_cannot_export(self):
        order = self._order(confirm=False)
        with self.assertRaisesRegex(UserError, "not confirmed"):
            order.action_karibu_export()

    def test_tonnage_must_match_order(self):
        order = self._order(qty=31.0, trucks=[
            {'vehicle_id': self.truck.id, 'qty_tons': 31.0},
            {'vehicle_id': self.truck.id, 'qty_tons': 9.0}])
        with self.assertRaisesRegex(UserError, "40.0 MT but the order is for 31.0 MT"):
            order.action_karibu_export()

    def test_tonnage_within_weighbridge_tolerance(self):
        order = self._order(qty=31.0, trucks=[
            {'vehicle_id': self.truck.id, 'qty_tons': 31.3}])
        order.action_karibu_export()
        self.assertEqual(len(order.nt_karibu_export_ids), 1)

    def test_tonnage_in_kg_is_converted(self):
        self.cement.uom_id = self.env.ref('uom.product_uom_kgm')
        order = self._order(qty=31000.0)
        order.order_line.product_uom_id = self.env.ref('uom.product_uom_kgm')
        order.action_karibu_export()
        self.assertEqual(len(order.nt_karibu_export_ids), 1)

    def test_lpo_reference_unique(self):
        self._order(ref='GPAL-12292')
        with self.assertRaises(ValidationError):
            self._order(ref='GPAL-12292', confirm=False)

    def test_lpo_reference_reusable_after_cancel(self):
        first = self._order(ref='GPAL-12292')
        first.button_cancel()
        self._order(ref='GPAL-12292')

    # -- export record --------------------------------------------------
    def test_export_file_and_history(self):
        order = self._order()
        action = order.action_karibu_export()
        export = order.nt_karibu_export_ids
        self.assertIn(f"id={export.id}", action['url'])
        self.assertEqual(export.file_name, 'GPAL_IR_-_10872-01.xlsx')
        self.assertEqual(export.state, 'exported')
        self.assertEqual(order.nt_karibu_state, 'exported')
        wb = load_workbook(io.BytesIO(base64.b64decode(export.file_data)), data_only=True)
        row = [c.value for c in wb['BulkUpload'][6]][:7]
        self.assertEqual(
            row, [1, 'GPAL-10872-01', 'CEMENT;32.5R;50KG-BAGS;(SIMBA IMARA)',
                  'BAG325R', 'T740EHQ', 4000539401, 31])

    def test_reexport_supersedes_previous(self):
        order = self._order()
        order.action_karibu_export()
        first = order.nt_karibu_export_ids
        order.action_karibu_export()
        self.assertEqual(first.state, 'superseded')
        self.assertEqual(len(order.nt_karibu_export_ids), 2)
        self.assertEqual(order.nt_karibu_state, 'exported')

    def test_status_flow(self):
        order = self._order()
        order.action_karibu_export()
        export = order.nt_karibu_export_ids
        export.action_mark_uploaded()
        export.supplier_ref = 'SOC260023661'
        export.action_mark_confirmed()
        self.assertEqual(order.nt_karibu_state, 'confirmed')
        with self.assertRaises(UserError):
            export.action_mark_uploaded()
        export.action_reset_exported()
        self.assertEqual(export.state, 'exported')

    def test_exported_order_cannot_be_deleted(self):
        order = self._order()
        order.action_karibu_export()
        order.button_cancel()
        with self.assertRaisesRegex(UserError, "export history must be kept"):
            order.unlink()
        self.assertTrue(order.exists())
