from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMultiChannelRentalI18n(TransactionCase):
    """Tests for multi-language support.  [I18N01–I18N10]"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1,
        )
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'I18N Test Pricelist',
            'company_id': cls.company.id,
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'I18N Test Customer',
            'email': 'i18n@test.example.com',
        })

        # Ensure FR and NL languages are active
        cls.env['res.lang']._activate_lang('fr_FR')
        cls.env['res.lang']._activate_lang('nl_NL')

        # Profile for kiosk
        cls.profile = cls.env['multi.channel.rental.profile'].create({
            'name': 'I18N Test Kiosk',
            'profile_type': 'kiosk',
            'company_id': cls.company.id,
            'warehouse_id': cls.warehouse.id,
            'pricelist_id': cls.pricelist.id,
            'enable_ticket_lookup_printing': True,
            'enable_dossier_ordering': True,
            'default_partner_id': cls.partner.id,
        })

    # ------------------------------------------------------------------
    # I18N01: .po files exist and are valid
    # ------------------------------------------------------------------
    def test_i18n01_po_files_exist(self):
        """[I18N01] Translation files exist for FR and NL."""
        import os
        module_path = os.path.dirname(os.path.dirname(__file__))
        i18n_path = os.path.join(module_path, 'i18n')

        self.assertTrue(os.path.isdir(i18n_path),
                        "i18n directory should exist")
        self.assertTrue(os.path.isfile(os.path.join(i18n_path, 'fr.po')),
                        "French translation file should exist")
        self.assertTrue(os.path.isfile(os.path.join(i18n_path, 'nl.po')),
                        "Dutch translation file should exist")
        self.assertTrue(
            os.path.isfile(os.path.join(i18n_path,
                                        'multi_channel_rental_flow.pot')),
            "POT template file should exist")

    # ------------------------------------------------------------------
    # I18N02: Translation files parse correctly
    # ------------------------------------------------------------------
    def test_i18n02_po_files_valid(self):
        """[I18N02] Translation .po files are syntactically valid."""
        import os
        import polib
        module_path = os.path.dirname(os.path.dirname(__file__))
        i18n_path = os.path.join(module_path, 'i18n')

        for lang_file in ['fr.po', 'nl.po']:
            path = os.path.join(i18n_path, lang_file)
            po = polib.pofile(path)
            translated = [e for e in po if e.msgstr and e.msgstr != e.msgid]
            self.assertGreater(
                len(translated), 100,
                f"{lang_file} should have at least 100 translated entries, "
                f"found {len(translated)}")

    # ------------------------------------------------------------------
    # I18N03: FR and NL languages are installed
    # ------------------------------------------------------------------
    def test_i18n03_languages_installed(self):
        """[I18N03] French and Dutch languages are installed."""
        installed = dict(self.env['res.lang'].get_installed())
        self.assertIn('fr_FR', installed,
                      "French should be installed")
        self.assertIn('nl_NL', installed,
                      "Dutch should be installed")

    # ------------------------------------------------------------------
    # I18N04: Kiosk controller lang helper works
    # ------------------------------------------------------------------
    def test_i18n04_get_kiosk_lang_valid(self):
        """[I18N04] _get_kiosk_lang returns valid lang codes."""
        from odoo.addons.multi_channel_rental_flow.controllers.kiosk import (
            MultiChannelRentalKiosk,
        )
        from unittest.mock import patch, MagicMock

        ctrl = MultiChannelRentalKiosk()

        # Mock request.env to return our test env
        mock_request = MagicMock()
        mock_request.env = self.env
        mock_request.env.lang = 'en_US'

        with patch(
            'odoo.addons.multi_channel_rental_flow.controllers.kiosk.request',
            mock_request,
        ):
            # Valid lang
            result = ctrl._get_kiosk_lang({'lang': 'fr_FR'})
            self.assertEqual(result, 'fr_FR')

            # Valid lang NL
            result = ctrl._get_kiosk_lang({'lang': 'nl_NL'})
            self.assertEqual(result, 'nl_NL')

            # Invalid lang falls back
            result = ctrl._get_kiosk_lang({'lang': 'xx_XX'})
            self.assertEqual(result, 'en_US')

            # No lang param falls back
            result = ctrl._get_kiosk_lang({})
            self.assertEqual(result, 'en_US')

    # ------------------------------------------------------------------
    # I18N05: Ticket lookup translations method exists and has structure
    # ------------------------------------------------------------------
    def test_i18n05_ticket_lookup_translations_method(self):
        """[I18N05] Ticket lookup controller has translations method."""
        from odoo.addons.multi_channel_rental_flow.controllers.kiosk import (
            MultiChannelRentalKiosk,
        )
        ctrl = MultiChannelRentalKiosk()
        self.assertTrue(
            hasattr(ctrl, '_get_ticket_lookup_translations'),
            "Controller should have _get_ticket_lookup_translations method")
        # Verify .po files contain the expected JS translation strings
        import os
        import polib
        module_path = os.path.dirname(os.path.dirname(__file__))
        pot_path = os.path.join(
            module_path, 'i18n', 'multi_channel_rental_flow.pot')
        po = polib.pofile(pot_path)
        pot_msgids = {e.msgid for e in po}

        expected_js_strings = [
            'Please enter both fields.',
            'Not found.',
            'Look Up',
            'No printer configured.',
            'Print Tickets',
            'Tickets printed successfully!',
        ]
        for s in expected_js_strings:
            self.assertIn(s, pot_msgids,
                          f"'{s}' should be extracted in POT (from _() call)")

    # ------------------------------------------------------------------
    # I18N06: Kiosk order translations method exists and has structure
    # ------------------------------------------------------------------
    def test_i18n06_kiosk_order_translations_method(self):
        """[I18N06] Kiosk order controller has translations method."""
        from odoo.addons.multi_channel_rental_flow.controllers.kiosk_order import (
            MultiChannelRentalKioskOrder,
        )
        ctrl = MultiChannelRentalKioskOrder()
        self.assertTrue(
            hasattr(ctrl, '_get_kiosk_order_translations'),
            "Controller should have _get_kiosk_order_translations method")
        # Verify .po files contain expected JS translation strings
        import os
        import polib
        module_path = os.path.dirname(os.path.dirname(__file__))
        pot_path = os.path.join(
            module_path, 'i18n', 'multi_channel_rental_flow.pot')
        po = polib.pofile(pot_path)
        pot_msgids = {e.msgid for e in po}

        expected_js_strings = [
            'Loading...',
            'No products available.',
            'No slots available.',
            'Your basket is empty.',
            'Email address is required.',
            'Processing payment...',
            'Payment failed.',
        ]
        for s in expected_js_strings:
            self.assertIn(s, pot_msgids,
                          f"'{s}' should be extracted in POT (from _() call)")

    # ------------------------------------------------------------------
    # I18N07: Website flow translations method exists
    # ------------------------------------------------------------------
    def test_i18n07_website_flow_translations_method(self):
        """[I18N07] Website flow controller has translations method."""
        from odoo.addons.multi_channel_rental_flow.controllers.website_flow import (
            MultiChannelRentalWebsite,
        )
        ctrl = MultiChannelRentalWebsite()
        self.assertTrue(
            hasattr(ctrl, '_get_website_flow_translations'),
            "Controller should have _get_website_flow_translations method")

    # ------------------------------------------------------------------
    # I18N08: FR .po has translations for key user-facing strings
    # ------------------------------------------------------------------
    def test_i18n08_fr_translations_present(self):
        """[I18N08] French .po has translations for key strings."""
        import os
        import polib
        module_path = os.path.dirname(os.path.dirname(__file__))
        fr_path = os.path.join(module_path, 'i18n', 'fr.po')
        po = polib.pofile(fr_path)

        # Build lookup
        lookup = {e.msgid: e.msgstr for e in po}

        key_strings = [
            'Welcome', 'Loading...', 'Your basket is empty.',
            'Payment failed.', 'Your Details',
        ]
        for s in key_strings:
            self.assertIn(s, lookup,
                          f"'{s}' should be in FR .po file")
            self.assertTrue(lookup[s],
                            f"'{s}' should have a French translation")

    # ------------------------------------------------------------------
    # I18N09: Error messages use _() for translation
    # ------------------------------------------------------------------
    def test_i18n09_error_messages_translatable(self):
        """[I18N09] API error messages use _() for translation."""
        # Verify that error message strings exist in the .po files
        import os
        import polib

        module_path = os.path.dirname(os.path.dirname(__file__))
        pot_path = os.path.join(
            module_path, 'i18n', 'multi_channel_rental_flow.pot')
        po = polib.pofile(pot_path)

        # These strings should be in the POT file (extracted from _() calls)
        expected_strings = [
            'Dossier not found.',
            'Item not found.',
            'Kiosk not available.',
        ]
        pot_msgids = {e.msgid for e in po}

        for s in expected_strings:
            self.assertIn(s, pot_msgids,
                          f"'{s}' should be in the POT file (from _() call)")

    # ------------------------------------------------------------------
    # I18N10: JS files reference TRANSLATIONS object
    # ------------------------------------------------------------------
    def test_i18n10_js_uses_translations_object(self):
        """[I18N10] JavaScript files reference the TRANSLATIONS object."""
        import os

        module_path = os.path.dirname(os.path.dirname(__file__))
        js_dir = os.path.join(module_path, 'static', 'src', 'js')

        for js_file in [
            'kiosk_order.js',
            'kiosk_ticket_lookup.js',
            'website_flow.js',
        ]:
            path = os.path.join(js_dir, js_file)
            with open(path, 'r') as f:
                content = f.read()
            self.assertIn(
                'TRANSLATIONS',
                content,
                f"{js_file} should reference the TRANSLATIONS object")
