from datetime import datetime, timedelta
from odoo.tests import Form
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestRentalDossier(TransactionCase):
    """Tests for rental.dossier, rental.dossier.slot, rental.dossier.item."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1,
        )
        cls.partner = cls.env['res.partner'].create({
            'name': 'MCRF Test Customer',
            'email': 'test@mcrf.example.com',
        })
        cls.pricelist = cls.env['product.pricelist'].search(
            [('company_id', 'in', (cls.company.id, False))], limit=1,
        )
        cls.product_rental = cls.env['product.product'].create({
            'name': 'MCRF Dossier Test Kayak',
            'type': 'consu',
            'list_price': 50.0,
            'use_in_multi_channel_rental_flow': True,
            'multi_channel_item_role': 'rental',
            'available_in_multi_channel_kiosk': True,
        })
        cls.product_addon = cls.env['product.product'].create({
            'name': 'MCRF Dossier Test Lunch',
            'type': 'consu',
            'list_price': 15.0,
            'use_in_multi_channel_rental_flow': True,
            'multi_channel_item_role': 'addon',
            'available_in_multi_channel_kiosk': True,
        })

        cls.now = datetime.now()
        cls.tomorrow_9 = (cls.now + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0,
        )
        cls.tomorrow_11 = cls.tomorrow_9 + timedelta(hours=2)
        cls.tomorrow_14 = cls.tomorrow_9 + timedelta(hours=5)
        cls.tomorrow_16 = cls.tomorrow_9 + timedelta(hours=7)

    # ------------------------------------------------------------------
    # Dossier creation & sequence
    # ------------------------------------------------------------------

    def _create_dossier(self, **kwargs):
        vals = {
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'source': 'backend',
        }
        vals.update(kwargs)
        return self.env['rental.dossier'].create(vals)

    def test_01_dossier_sequence(self):
        """Dossier name is auto-generated from sequence."""
        dossier = self._create_dossier()
        self.assertRegex(dossier.name, r'^(DOS/|RD)')
        self.assertNotEqual(dossier.name, '/')

    def test_02_dossier_initial_state(self):
        """New dossier starts in draft state."""
        dossier = self._create_dossier()
        self.assertEqual(dossier.state, 'draft')

    def test_03_dossier_currency_from_pricelist(self):
        """Currency is computed from the dossier's pricelist.

        Use a pricelist with an explicit currency that differs from the
        company currency so the assertion is deterministic and actually
        proves the currency is taken from the pricelist (and not from the
        company fallback in ``_compute_currency_id``). Relying on an
        arbitrary ``search(limit=1)`` pricelist is fragile: at install time
        the picked pricelist may have no currency, which correctly makes the
        dossier fall back to the company currency.
        """
        other_currency = self.env.ref('base.EUR')
        self.assertNotEqual(
            other_currency, self.company.currency_id,
            "Test needs a pricelist currency different from the company one.",
        )
        priced_list = self.env['product.pricelist'].create({
            'name': 'MCRF Currency Test Pricelist',
            'currency_id': other_currency.id,
            'company_id': self.company.id,
        })
        dossier = self._create_dossier(pricelist_id=priced_list.id)
        self.assertEqual(dossier.currency_id, other_currency)

    def test_03b_display_name_with_description(self):
        """Display name concatenates number and description."""
        dossier = self._create_dossier(description='Summer Kayak Weekend')
        self.assertIn(dossier.name, dossier.display_name)
        self.assertIn('Summer Kayak Weekend', dossier.display_name)

    def test_03c_display_name_without_description(self):
        """Display name shows just the number when no description."""
        dossier = self._create_dossier()
        self.assertEqual(dossier.display_name, dossier.name)

    def test_04_partner_email_onchange(self):
        """Email auto-fills from partner."""
        dossier = self.env['rental.dossier'].new({
            'partner_id': self.partner.id,
        })
        dossier._onchange_partner_id()
        self.assertEqual(dossier.partner_email, 'test@mcrf.example.com')

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def test_10_add_slots(self):
        """Slots can be added to a dossier."""
        dossier = self._create_dossier()
        slot = self.env['rental.dossier.slot'].create({
            'dossier_id': dossier.id,
            'start_datetime': self.tomorrow_9,
            'end_datetime': self.tomorrow_11,
            'warehouse_id': self.warehouse.id,
        })
        self.assertEqual(dossier.slot_count, 1)
        self.assertEqual(slot.state, 'draft')
        self.assertTrue(slot.name)

    def test_11_slot_date_validation(self):
        """Slot start must be before end."""
        dossier = self._create_dossier()
        with self.assertRaises(ValidationError):
            self.env['rental.dossier.slot'].create({
                'dossier_id': dossier.id,
                'start_datetime': self.tomorrow_11,
                'end_datetime': self.tomorrow_9,
                'warehouse_id': self.warehouse.id,
            })

    def test_12_multiple_slots(self):
        """Multiple slots with different timeslots."""
        dossier = self._create_dossier()
        self.env['rental.dossier.slot'].create({
            'dossier_id': dossier.id,
            'start_datetime': self.tomorrow_9,
            'end_datetime': self.tomorrow_11,
        })
        self.env['rental.dossier.slot'].create({
            'dossier_id': dossier.id,
            'start_datetime': self.tomorrow_14,
            'end_datetime': self.tomorrow_16,
        })
        self.assertEqual(dossier.slot_count, 2)

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------

    def test_20_add_item(self):
        """Items can be added to a dossier."""
        dossier = self._create_dossier()
        item = self.env['rental.dossier.item'].create({
            'dossier_id': dossier.id,
            'product_id': self.product_rental.id,
            'item_role': 'rental',
            'quantity': 2,
            'price_unit': 50.0,
        })
        self.assertEqual(item.state, 'draft')
        self.assertEqual(item.price_subtotal, 100.0)
        self.assertEqual(dossier.item_count, 1)

    def test_21_item_in_slot(self):
        """Items can be linked to a specific slot."""
        dossier = self._create_dossier()
        slot = self.env['rental.dossier.slot'].create({
            'dossier_id': dossier.id,
            'start_datetime': self.tomorrow_9,
            'end_datetime': self.tomorrow_11,
        })
        item = self.env['rental.dossier.item'].create({
            'dossier_id': dossier.id,
            'slot_id': slot.id,
            'product_id': self.product_rental.id,
            'item_role': 'rental',
            'quantity': 1,
            'price_unit': 50.0,
        })
        self.assertEqual(slot.item_count, 1)
        self.assertEqual(item.slot_id, slot)

    def test_22_item_product_uom(self):
        """Product UoM is auto-filled."""
        dossier = self._create_dossier()
        item = self.env['rental.dossier.item'].create({
            'dossier_id': dossier.id,
            'product_id': self.product_addon.id,
            'item_role': 'addon',
            'quantity': 3,
            'price_unit': 15.0,
        })
        self.assertEqual(item.product_uom_id, self.product_addon.uom_id)
        self.assertEqual(item.price_subtotal, 45.0)

    def test_23_item_coefficient_multiplier(self):
        """Coefficient and dynamic factor affect price preview."""
        dossier = self._create_dossier()
        item = self.env['rental.dossier.item'].create({
            'dossier_id': dossier.id,
            'product_id': self.product_rental.id,
            'item_role': 'rental',
            'quantity': 1,
            'price_unit': 75.0,
            'coefficient': 1.5,
            'dynamic_factor_percentage': 110.0,
        })
        self.assertAlmostEqual(item.dynamic_multiplier, 1.1, places=2)

    def test_24_item_quantity_must_be_positive(self):
        """Item quantity constraint rejects zero/negative."""
        dossier = self._create_dossier()
        with self.assertRaises(ValidationError):
            self.env['rental.dossier.item'].create({
                'dossier_id': dossier.id,
                'product_id': self.product_rental.id,
                'item_role': 'rental',
                'quantity': 0,
                'price_unit': 50.0,
            })

    # ------------------------------------------------------------------
    # Totals
    # ------------------------------------------------------------------

    def test_30_dossier_totals(self):
        """Dossier totals sum active items."""
        dossier = self._create_dossier()
        self.env['rental.dossier.item'].create({
            'dossier_id': dossier.id,
            'product_id': self.product_rental.id,
            'item_role': 'rental',
            'quantity': 2,
            'price_unit': 50.0,
        })
        self.env['rental.dossier.item'].create({
            'dossier_id': dossier.id,
            'product_id': self.product_addon.id,
            'item_role': 'addon',
            'quantity': 1,
            'price_unit': 15.0,
        })
        self.assertAlmostEqual(dossier.amount_untaxed, 115.0)
        self.assertAlmostEqual(dossier.amount_total, 115.0)

    def test_31_cancelled_items_excluded_from_totals(self):
        """Cancelled items are not included in totals."""
        dossier = self._create_dossier()
        self.env['rental.dossier.item'].create({
            'dossier_id': dossier.id,
            'product_id': self.product_rental.id,
            'item_role': 'rental',
            'quantity': 1,
            'price_unit': 50.0,
        })
        self.env['rental.dossier.item'].create({
            'dossier_id': dossier.id,
            'product_id': self.product_addon.id,
            'item_role': 'addon',
            'quantity': 1,
            'price_unit': 15.0,
            'state': 'cancelled',
        })
        self.assertAlmostEqual(dossier.amount_total, 50.0)

    def test_32_linked_order_total(self):
        """Linked order total sums sale order amounts."""
        dossier = self._create_dossier()
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
        })
        dossier.sale_order_ids = [(4, order.id)]
        # order total is 0 (no lines), just verify it computes
        self.assertEqual(dossier.linked_order_total, 0.0)

    # ------------------------------------------------------------------
    # Confirmation validation
    # ------------------------------------------------------------------

    def test_40_confirm_valid(self):
        """Draft dossier with required fields confirms successfully."""
        dossier = self._create_dossier()
        dossier.action_confirm()
        self.assertEqual(dossier.state, 'confirmed')

    def test_40b_confirm_requires_partner(self):
        """Confirmation fails without a customer."""
        dossier = self._create_dossier(partner_id=False)
        with self.assertRaises(UserError, msg="Customer is required"):
            dossier.action_confirm()

    def test_40c_confirm_website_requires_email(self):
        """Website dossier confirmation requires email."""
        dossier = self._create_dossier(
            source='website',
            partner_email=False,
        )
        with self.assertRaises(UserError, msg="email is required"):
            dossier.action_confirm()

    def test_40d_confirm_website_requires_profile(self):
        """Website dossier confirmation requires profile."""
        dossier = self._create_dossier(
            source='website',
            partner_email='test@example.com',
            profile_id=False,
        )
        with self.assertRaises(UserError, msg="Profile is required"):
            dossier.action_confirm()

    def test_40e_confirm_rental_items_require_warehouse(self):
        """Dossier with rental items requires warehouse."""
        dossier = self._create_dossier(warehouse_id=False)
        self.env['rental.dossier.item'].create({
            'dossier_id': dossier.id,
            'product_id': self.product_rental.id,
            'item_role': 'rental',
            'quantity': 1,
            'price_unit': 50.0,
        })
        with self.assertRaises(UserError, msg="Warehouse is required"):
            dossier.action_confirm()

    def test_41_request_payment(self):
        """Confirmed → payment_pending."""
        dossier = self._create_dossier()
        dossier.action_confirm()
        dossier.action_request_payment()
        self.assertEqual(dossier.state, 'payment_pending')

    def test_42_mark_paid(self):
        """Payment pending → paid."""
        dossier = self._create_dossier()
        dossier.action_confirm()
        dossier.action_request_payment()
        dossier.action_mark_paid()
        self.assertEqual(dossier.state, 'paid')

    def test_43_done(self):
        """Paid → done."""
        dossier = self._create_dossier()
        dossier.action_confirm()
        dossier.action_mark_paid()
        dossier.action_done()
        self.assertEqual(dossier.state, 'done')

    def test_44_cancel_and_reset(self):
        """Cancel cascades to items/slots, reset restores them."""
        dossier = self._create_dossier()
        self.env['rental.dossier.slot'].create({
            'dossier_id': dossier.id,
            'start_datetime': self.tomorrow_9,
            'end_datetime': self.tomorrow_11,
        })
        self.env['rental.dossier.item'].create({
            'dossier_id': dossier.id,
            'product_id': self.product_rental.id,
            'item_role': 'rental',
            'quantity': 1,
            'price_unit': 50.0,
        })
        dossier.action_cancel()
        self.assertEqual(dossier.state, 'cancelled')
        self.assertTrue(all(
            i.state == 'cancelled' for i in dossier.item_ids
        ))
        self.assertTrue(all(
            s.state == 'cancelled' for s in dossier.slot_ids
        ))

        # Reset restores everything to draft
        dossier.action_reset_to_draft()
        self.assertEqual(dossier.state, 'draft')
        self.assertTrue(all(
            i.state == 'draft' for i in dossier.item_ids
        ))
        self.assertTrue(all(
            s.state == 'draft' for s in dossier.slot_ids
        ))

    def test_45_cannot_cancel_done(self):
        """Done dossiers cannot be cancelled."""
        dossier = self._create_dossier()
        dossier.action_confirm()
        dossier.action_mark_paid()
        dossier.action_done()
        dossier.action_cancel()
        self.assertEqual(dossier.state, 'done')

    # ------------------------------------------------------------------
    # Sale order link
    # ------------------------------------------------------------------

    def test_50_sale_order_dossier_link(self):
        """Sale order can be linked to a dossier via M2M."""
        dossier = self._create_dossier()
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
        })
        dossier.sale_order_ids = [(4, order.id)]
        self.assertIn(order, dossier.sale_order_ids)
        self.assertEqual(dossier.sale_order_count, 1)

    def test_50b_sale_order_dossier_display(self):
        """Dossier display on sale order shows number and description."""
        dossier = self._create_dossier(description='Team Outing')
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'mcrf_dossier_ids': [(4, dossier.id)],
        })
        self.assertIn(dossier.name, order.mcrf_dossier_display)
        self.assertIn('Team Outing', order.mcrf_dossier_display)

    def test_50c_add_existing_order_to_dossier(self):
        """Existing sale orders can be manually added to a dossier."""
        dossier = self._create_dossier()
        order1 = self.env['sale.order'].create({
            'partner_id': self.partner.id,
        })
        order2 = self.env['sale.order'].create({
            'partner_id': self.partner.id,
        })
        dossier.sale_order_ids = [(4, order1.id), (4, order2.id)]
        self.assertEqual(dossier.sale_order_count, 2)
        self.assertIn(order1, dossier.sale_order_ids)
        self.assertIn(order2, dossier.sale_order_ids)

    def test_51_sale_order_line_item_link(self):
        """Sale order line can link to a dossier item."""
        dossier = self._create_dossier()
        item = self.env['rental.dossier.item'].create({
            'dossier_id': dossier.id,
            'product_id': self.product_rental.id,
            'item_role': 'rental',
            'quantity': 1,
            'price_unit': 50.0,
        })
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'mcrf_dossier_ids': [(4, dossier.id)],
        })
        line = self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': self.product_rental.id,
            'product_uom_qty': 1,
            'mcrf_dossier_item_id': item.id,
        })
        self.assertEqual(line.mcrf_dossier_item_id, item)

    # ------------------------------------------------------------------
    # Payment transaction link
    # ------------------------------------------------------------------

    def test_60_transaction_dossier_link(self):
        """Payment transaction can link to a dossier."""
        dossier = self._create_dossier()
        provider = self.env['payment.provider'].search(
            [('code', '=', 'demo')], limit=1,
        )
        if not provider:
            return
        payment_method = self.env['payment.method'].search([], limit=1)
        if not payment_method:
            return
        tx = self.env['payment.transaction'].create({
            'provider_id': provider.id,
            'payment_method_id': payment_method.id,
            'reference': 'MCRF-TEST-001',
            'amount': 50.0,
            'currency_id': dossier.currency_id.id,
            'partner_id': self.partner.id,
            'mcrf_dossier_id': dossier.id,
        })
        self.assertIn(tx, dossier.transaction_ids)
        self.assertEqual(dossier.transaction_count, 1)

    # ------------------------------------------------------------------
    # Event registration (soft dependency)
    # ------------------------------------------------------------------

    def test_70_registration_count_without_event(self):
        """Registration count is 0 when event module is not installed."""
        dossier = self._create_dossier()
        self.assertEqual(dossier.registration_count, 0)

    # ------------------------------------------------------------------
    # Copy
    # ------------------------------------------------------------------

    def test_80_dossier_copy(self):
        """Copied dossier gets a new sequence number."""
        dossier = self._create_dossier()
        copy = dossier.copy()
        self.assertNotEqual(copy.name, dossier.name)
        self.assertRegex(copy.name, r'^(DOS/|RD)')
        self.assertEqual(copy.state, 'draft')

    # ------------------------------------------------------------------
    # Recompute totals
    # ------------------------------------------------------------------

    def test_90_recompute_totals(self):
        """Recompute totals action does not raise."""
        dossier = self._create_dossier()
        self.env['rental.dossier.item'].create({
            'dossier_id': dossier.id,
            'product_id': self.product_rental.id,
            'item_role': 'rental',
            'quantity': 1,
            'price_unit': 50.0,
        })
        # Should not raise
        dossier.action_recompute_totals()
        self.assertAlmostEqual(dossier.amount_total, 50.0)

    # ------------------------------------------------------------------
    # Profile onchange  [DO13]
    # ------------------------------------------------------------------

    def test_91_profile_onchange_sets_defaults(self):
        """Profile onchange fills warehouse, pricelist and source."""
        profile = self.env['multi.channel.rental.profile'].create({
            'name': 'DO13 Test Profile',
            'profile_type': 'kiosk',
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
        })
        with Form(self.env['rental.dossier']) as f:
            f.partner_id = self.partner
            f.is_multi_channel = True
            f.profile_id = profile
        dossier = f.record
        self.assertEqual(dossier.warehouse_id, self.warehouse)
        self.assertEqual(dossier.pricelist_id, self.pricelist)
        self.assertEqual(dossier.source, 'kiosk')
        self.assertTrue(dossier.is_multi_channel)

    # ------------------------------------------------------------------
    # Item product onchange  [DI10]
    # ------------------------------------------------------------------

    def test_92_item_product_onchange_sets_role(self):
        """Item product onchange sets role from product config."""
        dossier = self._create_dossier()
        with Form(self.env['rental.dossier.item'].with_context(
            default_dossier_id=dossier.id,
        )) as f:
            f.product_id = self.product_rental
        item = f.record
        self.assertEqual(item.item_role, 'rental')

    # ------------------------------------------------------------------
    # Item pricing onchange  [DI11]
    # ------------------------------------------------------------------

    def test_93_item_pricing_onchange(self):
        """Pricing onchange computes preview price."""
        dossier = self._create_dossier()
        with Form(self.env['rental.dossier.item'].with_context(
            default_dossier_id=dossier.id,
        )) as f:
            f.product_id = self.product_rental
            f.quantity = 2
            f.coefficient = 1.5
            f.dynamic_factor_percentage = 100.0
        item = f.record
        # base price 50 × coeff 1.5 × dyn 1.0 = 75
        self.assertAlmostEqual(item.price_unit, 75.0, places=1)
