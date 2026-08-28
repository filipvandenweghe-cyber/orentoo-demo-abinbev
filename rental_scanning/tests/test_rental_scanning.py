from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRentalScanningCommon(TransactionCase):
    """Acceptance tests T-01..T-14 for the rental_scanning reconciliation core.

    The Barcode-client JS layer is covered separately by tours; these tests
    exercise the server logic reachable from both the Barcode client and the
    backend action.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        cls.warehouse = cls.env['stock.warehouse'].search([], limit=1)
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.customer_loc = cls.env.ref('stock.stock_location_customers')

        # A sibling internal location NOT under the picking source (for T-06).
        cls.other_loc = cls.env['stock.location'].create({
            'name': 'RS Other',
            'usage': 'internal',
            'location_id': cls.warehouse.view_location_id.id,
        })

        # Products ----------------------------------------------------------
        cls.glas = cls.env['product.product'].create({
            'name': 'Glas', 'type': 'consu', 'is_storable': True,
        })
        cls.plate = cls.env['product.product'].create({
            'name': 'Plate', 'type': 'consu', 'is_storable': True,
        })
        cls.eurobak = cls.env['product.product'].create({
            'name': 'Eurobak 40', 'type': 'consu', 'is_storable': True,
            'tracking': 'serial',
        })

        # Rental set: 1 Eurobak + 40 Glas, with a barcode (for set-scan) ----
        cls.set_tmpl = cls.env['product.template'].create({
            'name': '40 Glazen in Eurobak', 'type': 'consu',
            'is_storable': True, 'is_rental_set': True,
        })
        cls.env['rental.set.component'].create([
            {'set_product_tmpl_id': cls.set_tmpl.id,
             'product_id': cls.eurobak.id, 'quantity': 1},
            {'set_product_tmpl_id': cls.set_tmpl.id,
             'product_id': cls.glas.id, 'quantity': 40},
        ])
        cls.set_product = cls.set_tmpl.product_variant_id
        cls.set_product.barcode = 'SET-40GLAZEN'

        # Base loose stock --------------------------------------------------
        cls._set_stock(cls.glas, cls.stock_loc, 500)

    # ── helpers ────────────────────────────────────────────────────────────

    @classmethod
    def _set_stock(cls, product, location, qty, lot=None, package=None):
        vals = {
            'product_id': product.id,
            'location_id': location.id,
            'inventory_quantity': qty,
        }
        if lot:
            vals['lot_id'] = lot.id
        if package:
            vals['package_id'] = package.id
        quant = cls.env['stock.quant'].with_context(
            inventory_mode=True).create(vals)
        quant.action_apply_inventory()
        return quant

    @classmethod
    def _new_serial(cls, name):
        return cls.env['stock.lot'].create({
            'name': name, 'product_id': cls.eurobak.id})

    def _make_package(self, name, contents, location=None):
        """contents = [(product, qty, lot_or_None)]."""
        location = location or self.stock_loc
        package = self.env['stock.package'].create({'name': name})
        for product, qty, lot in contents:
            self._set_stock(product, location, qty, lot=lot, package=package)
        return package

    def _make_delivery(self, demand, reserve=False):
        """demand = [(product, qty)]; returns a confirmed picking.

        reserve=False -> unreserved (clean slate);
        reserve=True  -> reserved ("Ready"), i.e. move-lines with
        quantity set and picked=False (the real-world case).
        """
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.out_type_id.id,
            'location_id': self.stock_loc.id,
            'location_dest_id': self.customer_loc.id,
        })
        for product, qty in demand:
            self.env['stock.move'].create({
                'name': product.name,
                'product_id': product.id,
                'product_uom_qty': qty,
                'product_uom': product.uom_id.id,
                'picking_id': picking.id,
                'location_id': self.stock_loc.id,
                'location_dest_id': self.customer_loc.id,
            })
        picking.action_confirm()
        if reserve:
            picking.action_assign()
        else:
            picking.do_unreserve()  # clean slate: no reserved lines
        return picking

    def _move(self, picking, product):
        return picking.move_ids.filtered(lambda m: m.product_id == product)[:1]


class TestRentalScanning(TestRentalScanningCommon):

    def test_01_exact_match_single_step(self):
        serial = self._new_serial('EB-0001')
        pkg = self._make_package('BAK01', [
            (self.eurobak, 1, serial), (self.glas, 40, None)])
        picking = self._make_delivery([(self.eurobak, 1), (self.glas, 40)])

        res = picking.rental_scanning_scan('BAK01')

        self.assertEqual(res['status'], 'applied')
        self.assertEqual(self._move(picking, self.glas).quantity, 40)
        eb = self._move(picking, self.eurobak)
        self.assertEqual(eb.quantity, 1)
        line = eb.move_line_ids[:1]
        self.assertEqual(line.package_id, pkg)
        self.assertEqual(line.lot_id, serial)

    def test_03_extra_product_rejected(self):
        pkg = self._make_package('BAK03', [
            (self.glas, 40, None), (self.plate, 4, None)])
        picking = self._make_delivery([(self.glas, 40)])
        with self.assertRaises(UserError):
            picking.rental_scanning_scan('BAK03')
        # Nothing applied.
        self.assertEqual(self._move(picking, self.glas).quantity, 0)

    def test_04_overflow_prompts_split(self):
        self._make_package('BAK04', [(self.glas, 60, None)])
        picking = self._make_delivery([(self.glas, 40)])

        res = picking.rental_scanning_scan('BAK04')
        self.assertEqual(res['status'], 'need_split')
        self.assertEqual(self._move(picking, self.glas).quantity, 0)

        res2 = picking.rental_scanning_scan('BAK04', allow_split=True)
        self.assertEqual(res2['status'], 'partial')
        self.assertEqual(self._move(picking, self.glas).quantity, 40)

    def test_05_partial_accepted(self):
        self._make_package('BAK05', [(self.glas, 20, None)])
        picking = self._make_delivery([(self.glas, 40)])
        res = picking.rental_scanning_scan('BAK05')
        self.assertEqual(res['status'], 'applied')
        self.assertEqual(self._move(picking, self.glas).quantity, 20)
        self.assertEqual(picking._rs_remaining_for(self.glas.id), 20)

    def test_06_wrong_location_rejected(self):
        self._make_package('BAK06', [(self.glas, 40, None)],
                           location=self.other_loc)
        picking = self._make_delivery([(self.glas, 40)])
        with self.assertRaises(UserError):
            picking.rental_scanning_scan('BAK06')

    def test_09_set_barcode_fills_components(self):
        picking = self._make_delivery([(self.eurobak, 1), (self.glas, 40)])
        res = picking.rental_scanning_scan('SET-40GLAZEN')
        self.assertEqual(res['kind'], 'set')
        self.assertEqual(res['status'], 'applied')
        self.assertEqual(self._move(picking, self.glas).quantity, 40)
        self.assertEqual(self._move(picking, self.eurobak).quantity, 1)

    def test_10_serial_scan_resolves_to_container(self):
        serial = self._new_serial('EB-0010')
        pkg = self._make_package('BAK10', [
            (self.eurobak, 1, serial), (self.glas, 40, None)])
        picking = self._make_delivery([(self.eurobak, 1), (self.glas, 40)])

        res = picking.rental_scanning_scan('EB-0010')
        self.assertEqual(res['kind'], 'package')
        self.assertEqual(res['status'], 'applied')
        self.assertEqual(self._move(picking, self.glas).quantity, 40)
        eb = self._move(picking, self.eurobak)
        self.assertEqual(eb.quantity, 1)
        self.assertEqual(eb.move_line_ids[:1].package_id, pkg)

    def test_13_loose_serial_adds_only_that_product(self):
        # Serial NOT in any package -> standard single-serial behaviour.
        serial = self._new_serial('EB-0013')
        self._set_stock(self.eurobak, self.stock_loc, 1, lot=serial)
        picking = self._make_delivery([(self.eurobak, 1), (self.glas, 40)])

        res = picking.rental_scanning_scan('EB-0013')
        self.assertEqual(res['kind'], 'product')
        eb = self._move(picking, self.eurobak)
        self.assertEqual(eb.quantity, 1)
        self.assertEqual(eb.move_line_ids[:1].lot_id, serial)
        # Nothing else was touched.
        self.assertEqual(self._move(picking, self.glas).quantity, 0)

    def test_14_partial_then_backorder(self):
        serial = self._new_serial('EB-0014')
        self._make_package('BAK14', [
            (self.eurobak, 1, serial), (self.glas, 20, None)])
        picking = self._make_delivery([(self.eurobak, 1), (self.glas, 40)])

        res = picking.rental_scanning_scan('BAK14')
        self.assertEqual(res['status'], 'applied')
        self.assertEqual(self._move(picking, self.glas).quantity, 20)
        self.assertEqual(picking._rs_remaining_for(self.glas.id), 20)

        # Validate -> a backorder carries the remaining 20 glasses.
        action = picking.button_validate()
        if isinstance(action, dict) and action.get('res_model') == \
                'stock.backorder.confirmation':
            wiz = self.env['stock.backorder.confirmation'].with_context(
                action['context']).create({})
            wiz.process()

        self.assertEqual(picking.state, 'done')
        backorder = self.env['stock.picking'].search([
            ('backorder_id', '=', picking.id)])
        self.assertTrue(backorder, "A backorder must carry the remaining demand")
        self.assertEqual(
            sum(backorder.move_ids.filtered(
                lambda m: m.product_id == self.glas).mapped('product_uom_qty')),
            20)

    def test_15_works_on_reserved_picking(self):
        # Real-world case: picking already reserved -> move.quantity == demand
        # with picked=False.  The scan must still recognise the demand
        # (regression: previously mis-flagged demanded products as "not
        # required").
        serial = self._new_serial('EB-0015')
        pkg = self._make_package('BAK15', [
            (self.eurobak, 1, serial), (self.glas, 40, None)])
        picking = self._make_delivery(
            [(self.eurobak, 1), (self.glas, 40)], reserve=True)
        self.assertTrue(all(not l.picked for l in picking.move_line_ids),
                        "precondition: reserved but nothing picked")

        res = picking.rental_scanning_scan('BAK15')

        self.assertEqual(res['status'], 'applied')
        eb = self._move(picking, self.eurobak)
        self.assertEqual(eb.quantity, 1)
        picked = eb.move_line_ids.filtered('quantity')
        self.assertTrue(all(l.picked for l in picked))
        self.assertEqual(picked[:1].package_id, pkg)
        self.assertEqual(self._move(picking, self.glas).quantity, 40)

    def test_16_rescan_same_package_is_idempotent(self):
        serial = self._new_serial('EB-0016')
        self._make_package('BAK16', [
            (self.eurobak, 1, serial), (self.glas, 40, None)])
        picking = self._make_delivery([(self.eurobak, 1), (self.glas, 40)])
        picking.rental_scanning_scan('BAK16')
        res = picking.rental_scanning_scan('BAK16')  # again
        self.assertEqual(res['status'], 'applied')
        self.assertEqual(self._move(picking, self.glas).quantity, 40)
        self.assertEqual(self._move(picking, self.eurobak).quantity, 1)

    def test_17_remove_scanned_package(self):
        serial = self._new_serial('EB-0017')
        pkg = self._make_package('BAK17', [
            (self.eurobak, 1, serial), (self.glas, 40, None)])
        picking = self._make_delivery([(self.eurobak, 1), (self.glas, 40)])
        picking.rental_scanning_scan('BAK17')
        self.assertIn(pkg, picking.rental_scanning_package_ids)
        self.assertEqual(self._move(picking, self.glas).quantity, 40)

        picking.rental_scanning_remove_package('BAK17')
        self.assertNotIn(pkg, picking.rental_scanning_package_ids)
        self.assertEqual(self._move(picking, self.glas).quantity, 0)
        self.assertEqual(self._move(picking, self.eurobak).quantity, 0)

    def test_18_swap_partial_for_full(self):
        # Q2: remove a partial package and pick a full one (no mixing).
        s1 = self._new_serial('EB-0018a')
        self._make_package('BAKPART', [
            (self.eurobak, 1, s1), (self.glas, 35, None)])
        s2 = self._new_serial('EB-0018b')
        self._make_package('BAKFULL', [
            (self.eurobak, 1, s2), (self.glas, 40, None)])
        picking = self._make_delivery([(self.eurobak, 1), (self.glas, 40)])

        picking.rental_scanning_scan('BAKPART')
        self.assertEqual(self._move(picking, self.glas).quantity, 35)

        picking.rental_scanning_remove_package('BAKPART')
        picking.rental_scanning_scan('BAKFULL')
        self.assertEqual(self._move(picking, self.glas).quantity, 40)
        self.assertEqual(self._move(picking, self.eurobak).quantity, 1)
        glas_line = self._move(picking, self.glas).move_line_ids.filtered(
            'quantity')[:1]
        self.assertEqual(glas_line.package_id.name, 'BAKFULL')
