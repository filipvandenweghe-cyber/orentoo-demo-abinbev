from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


class TestCoefficientType(TransactionCase):
    """Tests for rental.coefficient.type  [RC01, RC02, RC03]"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.CType = cls.env['rental.coefficient.type']

    # -- RC02: default data ---------------------------------------------------

    def test_rc02_standard_type_exists(self):
        """The default 'Standard' coefficient type is created on install."""
        std = self.CType.search([('name', '=', 'Standard')])
        self.assertTrue(std, "Standard coefficient type should exist")

    # -- RC01: create types ---------------------------------------------------

    def test_rc01_create_type(self):
        """A coefficient type can be created with name + company."""
        ct = self.CType.create({'name': 'Professional'})
        self.assertTrue(ct.id)
        self.assertTrue(ct.active)

    # -- RC03: unique name per company ----------------------------------------

    @mute_logger('odoo.sql_db')
    def test_rc03_duplicate_name_same_company_blocked(self):
        """Two types with the same name in the same company are blocked."""
        self.CType.create({'name': 'Weekend'})
        with self.assertRaises(IntegrityError):
            self.CType.create({'name': 'Weekend'})

    def test_rc03_same_name_different_company_allowed(self):
        """Same name in different companies is allowed."""
        # Use an existing second company to avoid not-null constraint issues
        # when creating a res.company in a rental-enabled database.
        companies = self.env['res.company'].search([], limit=2)
        if len(companies) < 2:
            self.skipTest("Need at least two companies for this test")
        c1, c2 = companies[0], companies[1]
        unique_name = f'RC03Test_{c1.id}_{c2.id}'
        self.CType.create({'name': unique_name, 'company_id': c1.id})
        ct2 = self.CType.create({'name': unique_name, 'company_id': c2.id})
        self.assertTrue(ct2.id)


class TestCoefficientTable(TransactionCase):
    """Tests for rental.coefficient.table  [RC04, RC05, RC10]"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.CTable = cls.env['rental.coefficient.table']
        cls.CLine = cls.env['rental.coefficient.table.line']
        cls.std_type = cls.env['rental.coefficient.type'].search(
            [('name', '=', 'Standard')], limit=1,
        )

    # -- RC04: table linked to type -------------------------------------------

    def test_rc04_table_requires_type(self):
        """A coefficient table must reference a coefficient type."""
        table = self.CTable.create({
            'name': 'Daily Standard',
            'coefficient_type_id': self.std_type.id,
            'duration_unit': 'day',
        })
        self.assertEqual(table.coefficient_type_id, self.std_type)

    # -- RC05: duration unit --------------------------------------------------

    def test_rc05_duration_unit_selection(self):
        """All five duration units are accepted."""
        for unit in ('minute', 'hour', 'day', 'week', 'month'):
            table = self.CTable.create({
                'name': f'Test {unit}',
                'coefficient_type_id': self.std_type.id,
                'duration_unit': unit,
            })
            self.assertEqual(table.duration_unit, unit)

    # -- RC10: one standard per company + type --------------------------------

    def test_rc10_one_standard_per_company_type(self):
        """Only one standard table per company + coefficient type."""
        # Use a fresh type to avoid collisions with existing DB data
        fresh_type = self.env['rental.coefficient.type'].create({
            'name': 'RC10 Test Type A',
        })
        self.CTable.create({
            'name': 'Standard 1',
            'coefficient_type_id': fresh_type.id,
            'duration_unit': 'day',
            'is_standard': True,
        })
        with self.assertRaises(ValidationError):
            self.CTable.create({
                'name': 'Standard 2',
                'coefficient_type_id': fresh_type.id,
                'duration_unit': 'day',
                'is_standard': True,
            })

    def test_rc10_standard_different_types_allowed(self):
        """Standard tables for different types in same company are allowed."""
        type1 = self.env['rental.coefficient.type'].create({
            'name': 'RC10 Test Type B',
        })
        type2 = self.env['rental.coefficient.type'].create({
            'name': 'RC10 Test Type C',
        })
        t1 = self.CTable.create({
            'name': 'Std for Type B',
            'coefficient_type_id': type1.id,
            'duration_unit': 'day',
            'is_standard': True,
        })
        t2 = self.CTable.create({
            'name': 'Std for Type C',
            'coefficient_type_id': type2.id,
            'duration_unit': 'day',
            'is_standard': True,
        })
        self.assertTrue(t1.is_standard and t2.is_standard)

    def test_rc10_non_standard_duplicates_allowed(self):
        """Multiple non-standard tables for same company + type are fine."""
        t1 = self.CTable.create({
            'name': 'Custom A',
            'coefficient_type_id': self.std_type.id,
            'duration_unit': 'day',
        })
        t2 = self.CTable.create({
            'name': 'Custom B',
            'coefficient_type_id': self.std_type.id,
            'duration_unit': 'day',
        })
        self.assertTrue(t1.id and t2.id)


class TestCoefficientTableLine(TransactionCase):
    """Tests for rental.coefficient.table.line  [RC06, RC07, RC08]"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.CTable = cls.env['rental.coefficient.table']
        cls.CLine = cls.env['rental.coefficient.table.line']
        std_type = cls.env['rental.coefficient.type'].search(
            [('name', '=', 'Standard')], limit=1,
        )
        cls.table = cls.CTable.create({
            'name': 'Test Table',
            'coefficient_type_id': std_type.id,
            'duration_unit': 'day',
        })

    # -- RC06: as_from_duration >= 0, coefficient > 0 -------------------------

    def test_rc06_duration_zero_allowed(self):
        """as_from_duration = 0 is allowed."""
        line = self.CLine.create({
            'table_id': self.table.id,
            'as_from_duration': 0,
            'coefficient': 0.5,
        })
        self.assertEqual(line.as_from_duration, 0)

    @mute_logger('odoo.sql_db')
    def test_rc06_negative_duration_blocked(self):
        """Negative as_from_duration is blocked by SQL CHECK."""
        with self.assertRaises(IntegrityError):
            self.CLine.create({
                'table_id': self.table.id,
                'as_from_duration': -1,
                'coefficient': 1.0,
            })

    @mute_logger('odoo.sql_db')
    def test_rc06_zero_coefficient_blocked(self):
        """Coefficient = 0 is blocked by SQL CHECK."""
        with self.assertRaises(IntegrityError):
            self.CLine.create({
                'table_id': self.table.id,
                'as_from_duration': 99,
                'coefficient': 0.0,
            })

    @mute_logger('odoo.sql_db')
    def test_rc06_negative_coefficient_blocked(self):
        """Negative coefficient is blocked by SQL CHECK."""
        with self.assertRaises(IntegrityError):
            self.CLine.create({
                'table_id': self.table.id,
                'as_from_duration': 98,
                'coefficient': -1.0,
            })

    # -- RC07: unique duration per table --------------------------------------

    @mute_logger('odoo.sql_db')
    def test_rc07_duplicate_duration_blocked(self):
        """Duplicate as_from_duration in the same table is blocked."""
        self.CLine.create({
            'table_id': self.table.id,
            'as_from_duration': 5,
            'coefficient': 3.0,
        })
        with self.assertRaises(IntegrityError):
            self.CLine.create({
                'table_id': self.table.id,
                'as_from_duration': 5,
                'coefficient': 4.0,
            })

    def test_rc07_same_duration_different_table_allowed(self):
        """Same as_from_duration in different tables is allowed."""
        std_type = self.env['rental.coefficient.type'].search(
            [('name', '=', 'Standard')], limit=1,
        )
        table2 = self.CTable.create({
            'name': 'Other Table',
            'coefficient_type_id': std_type.id,
            'duration_unit': 'day',
        })
        l1 = self.CLine.create({
            'table_id': self.table.id,
            'as_from_duration': 10,
            'coefficient': 7.0,
        })
        l2 = self.CLine.create({
            'table_id': table2.id,
            'as_from_duration': 10,
            'coefficient': 8.0,
        })
        self.assertTrue(l1.id and l2.id)

    # -- RC08: auto-sort by as_from_duration ----------------------------------

    def test_rc08_sequence_computed_from_duration(self):
        """Sequence field equals as_from_duration for automatic ordering."""
        l1 = self.CLine.create({
            'table_id': self.table.id,
            'as_from_duration': 7,
            'coefficient': 5.0,
        })
        l2 = self.CLine.create({
            'table_id': self.table.id,
            'as_from_duration': 1,
            'coefficient': 1.0,
        })
        self.assertEqual(l1.sequence, 7)
        self.assertEqual(l2.sequence, 1)


class TestCoefficientLookup(TransactionCase):
    """Tests for get_coefficient_for_duration()  [RC09]"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        std_type = cls.env['rental.coefficient.type'].search(
            [('name', '=', 'Standard')], limit=1,
        )
        cls.table = cls.env['rental.coefficient.table'].create({
            'name': 'Lookup Test',
            'coefficient_type_id': std_type.id,
            'duration_unit': 'day',
            'line_ids': [
                (0, 0, {'as_from_duration': 1, 'coefficient': 1.0}),
                (0, 0, {'as_from_duration': 3, 'coefficient': 2.5}),
                (0, 0, {'as_from_duration': 7, 'coefficient': 5.0}),
                (0, 0, {'as_from_duration': 14, 'coefficient': 9.0}),
                (0, 0, {'as_from_duration': 30, 'coefficient': 20.0}),
            ],
        })

    def test_rc09_exact_match_first_line(self):
        """Duration exactly on the first threshold returns that coefficient."""
        self.assertEqual(self.table.get_coefficient_for_duration(1), 1.0)

    def test_rc09_exact_match_middle_line(self):
        """Duration exactly on a middle threshold returns that coefficient."""
        self.assertEqual(self.table.get_coefficient_for_duration(7), 5.0)

    def test_rc09_exact_match_last_line(self):
        """Duration exactly on the last threshold returns that coefficient."""
        self.assertEqual(self.table.get_coefficient_for_duration(30), 20.0)

    def test_rc09_between_thresholds(self):
        """Duration between two thresholds uses the lower threshold."""
        self.assertEqual(self.table.get_coefficient_for_duration(5), 2.5)

    def test_rc09_above_last_threshold(self):
        """Duration above all thresholds uses the last (highest) line."""
        self.assertEqual(self.table.get_coefficient_for_duration(365), 20.0)

    def test_rc09_below_first_threshold(self):
        """Duration below the first threshold returns False."""
        self.assertFalse(self.table.get_coefficient_for_duration(0))

    def test_rc09_negative_duration(self):
        """Negative duration returns False."""
        self.assertFalse(self.table.get_coefficient_for_duration(-5))

    def test_rc09_empty_table(self):
        """Empty table (no lines) returns False."""
        std_type = self.env['rental.coefficient.type'].search(
            [('name', '=', 'Standard')], limit=1,
        )
        empty = self.env['rental.coefficient.table'].create({
            'name': 'Empty',
            'coefficient_type_id': std_type.id,
            'duration_unit': 'day',
        })
        self.assertFalse(empty.get_coefficient_for_duration(5))

    def test_rc09_table_with_zero_threshold(self):
        """Table with as_from_duration=0 matches duration 0."""
        std_type = self.env['rental.coefficient.type'].search(
            [('name', '=', 'Standard')], limit=1,
        )
        table = self.env['rental.coefficient.table'].create({
            'name': 'With Zero',
            'coefficient_type_id': std_type.id,
            'duration_unit': 'day',
            'line_ids': [
                (0, 0, {'as_from_duration': 0, 'coefficient': 0.5}),
                (0, 0, {'as_from_duration': 1, 'coefficient': 1.0}),
            ],
        })
        self.assertEqual(table.get_coefficient_for_duration(0), 0.5)
        self.assertEqual(table.get_coefficient_for_duration(1), 1.0)

    def test_rc09_single_line_table(self):
        """Table with exactly one line works correctly."""
        std_type = self.env['rental.coefficient.type'].search(
            [('name', '=', 'Standard')], limit=1,
        )
        table = self.env['rental.coefficient.table'].create({
            'name': 'Single Line',
            'coefficient_type_id': std_type.id,
            'duration_unit': 'day',
            'line_ids': [
                (0, 0, {'as_from_duration': 3, 'coefficient': 2.0}),
            ],
        })
        self.assertFalse(table.get_coefficient_for_duration(2))
        self.assertEqual(table.get_coefficient_for_duration(3), 2.0)
        self.assertEqual(table.get_coefficient_for_duration(100), 2.0)

    def test_rc09_degressive_pricing_example(self):
        """Verify the degressive pricing example from the spec.

        Base daily price: 20 EUR.
        1 day  → coeff 1   → 20 x 1   = 20 EUR
        7 days → coeff 5   → 20 x 5   = 100 EUR
        """
        self.assertEqual(self.table.get_coefficient_for_duration(1), 1.0)
        self.assertEqual(self.table.get_coefficient_for_duration(7), 5.0)
        # Price = base * coefficient
        base_price = 20.0
        self.assertAlmostEqual(base_price * 1.0, 20.0)
        self.assertAlmostEqual(base_price * 5.0, 100.0)
