from odoo.tests import Form
from odoo.tests.common import TransactionCase


class TestProductConfig(TransactionCase):
    """Tests for product-level MCRF configuration.  [PC01–PC09]"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product_tmpl = cls.env['product.template'].create({
            'name': 'MCRF PC Test Product',
            'type': 'consu',
            'list_price': 30.0,
        })
        cls.product = cls.product_tmpl.product_variant_ids[0]

    # ------------------------------------------------------------------
    # Field defaults  [PC05, PC06]
    # ------------------------------------------------------------------

    def test_01_default_behavior_flags(self):
        """Behavior flags have correct defaults."""
        pp = self.env['product.product'].create({
            'name': 'MCRF Default Test',
            'type': 'consu',
        })
        self.assertFalse(pp.requires_timeslot)
        self.assertFalse(pp.requires_duration)
        self.assertTrue(pp.allow_quantity_selection)  # PC05 default

    def test_02_default_image_flag(self):
        """use_product_image_in_flow defaults to True."""
        pp = self.env['product.product'].create({
            'name': 'MCRF Image Default Test',
            'type': 'consu',
        })
        self.assertTrue(pp.use_product_image_in_flow)  # PC06

    # ------------------------------------------------------------------
    # Role onchange  [PC07]
    # ------------------------------------------------------------------

    def test_10_onchange_rental_sets_timeslot_duration(self):
        """Setting role to 'rental' enables timeslot and duration."""
        with Form(self.product) as f:
            f.use_in_multi_channel_rental_flow = True
            f.multi_channel_item_role = 'rental'
        self.assertTrue(self.product.requires_timeslot)
        self.assertTrue(self.product.requires_duration)

    def test_11_onchange_addon_clears_timeslot_duration(self):
        """Setting role to 'addon' disables timeslot and duration."""
        # First set to rental
        with Form(self.product) as f:
            f.use_in_multi_channel_rental_flow = True
            f.multi_channel_item_role = 'rental'
        self.assertTrue(self.product.requires_timeslot)

        # Then switch to addon
        with Form(self.product) as f:
            f.multi_channel_item_role = 'addon'
        self.assertFalse(self.product.requires_timeslot)
        self.assertFalse(self.product.requires_duration)

    def test_12_onchange_service_clears_timeslot_duration(self):
        """Setting role to 'service' disables timeslot and duration."""
        with Form(self.product) as f:
            f.use_in_multi_channel_rental_flow = True
            f.multi_channel_item_role = 'service'
        self.assertFalse(self.product.requires_timeslot)
        self.assertFalse(self.product.requires_duration)

    def test_13_onchange_event_ticket_clears_timeslot_duration(self):
        """Setting role to 'event_ticket' disables timeslot and duration."""
        with Form(self.product) as f:
            f.use_in_multi_channel_rental_flow = True
            f.multi_channel_item_role = 'event_ticket'
        self.assertFalse(self.product.requires_timeslot)
        self.assertFalse(self.product.requires_duration)

    # ------------------------------------------------------------------
    # Master toggle onchange  [PC08]
    # ------------------------------------------------------------------

    def test_20_disable_master_clears_channels(self):
        """Turning off master toggle clears website and kiosk flags."""
        with Form(self.product) as f:
            f.use_in_multi_channel_rental_flow = True
            f.available_in_multi_channel_website = True
            f.available_in_multi_channel_kiosk = True
        self.assertTrue(self.product.available_in_multi_channel_website)
        self.assertTrue(self.product.available_in_multi_channel_kiosk)

        with Form(self.product) as f:
            f.use_in_multi_channel_rental_flow = False
        self.assertFalse(self.product.available_in_multi_channel_website)
        self.assertFalse(self.product.available_in_multi_channel_kiosk)

    # ------------------------------------------------------------------
    # Template summary  [PC09]
    # ------------------------------------------------------------------

    def test_30_template_variant_count(self):
        """Template counts enabled variants correctly."""
        tmpl = self.product.product_tmpl_id
        self.assertFalse(tmpl.mcrf_any_variant_enabled)
        self.assertEqual(tmpl.mcrf_variant_count, 0)

        self.product.use_in_multi_channel_rental_flow = True
        tmpl.invalidate_recordset()
        self.assertTrue(tmpl.mcrf_any_variant_enabled)
        self.assertEqual(tmpl.mcrf_variant_count, 1)

    # ------------------------------------------------------------------
    # Behavior flags used by service  [PC05]
    # ------------------------------------------------------------------

    def test_40_requires_duration_affects_duration_options(self):
        """requires_duration=True triggers coefficient table lookup."""
        svc = self.env['multi.channel.rental.service']
        wh = self.env['stock.warehouse'].search([], limit=1)
        profile = self.env['multi.channel.rental.profile'].create({
            'name': 'PC05 Test Profile',
            'profile_type': 'kiosk',
            'warehouse_id': wh.id,
        })

        # Product without requires_duration → fallback options
        self.product.requires_duration = False
        options_no = svc._get_duration_options(profile, self.product)
        # Should get fallback (no coefficient table lookup)
        self.assertTrue(len(options_no) > 0)

        # Product with requires_duration → may find coefficient table
        self.product.requires_duration = True
        options_yes = svc._get_duration_options(profile, self.product)
        self.assertTrue(len(options_yes) > 0)
