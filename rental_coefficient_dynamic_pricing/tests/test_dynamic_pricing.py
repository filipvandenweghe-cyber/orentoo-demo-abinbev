from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tools import mute_logger
from psycopg2 import IntegrityError


class TestDynamicPricingTable(TransactionCase):
    """Tests for rental.dynamic.pricing.table  [RD01]"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.DPTable = cls.env['rental.dynamic.pricing.table']

    def test_rd01_create_table(self):
        """A dynamic pricing table can be created."""
        table = self.DPTable.create({
            'name': 'Summer 2026',
            'selection_calendar': 'start_hour',
        })
        self.assertTrue(table.id)
        self.assertEqual(table.selection_calendar, 'start_hour')

    def test_rd10_selection_calendar_options(self):
        """Both granularity options are accepted."""
        t1 = self.DPTable.create({
            'name': 'Hourly',
            'selection_calendar': 'start_hour',
        })
        t2 = self.DPTable.create({
            'name': 'Daily',
            'selection_calendar': 'start_day',
        })
        self.assertEqual(t1.selection_calendar, 'start_hour')
        self.assertEqual(t2.selection_calendar, 'start_day')


class TestDynamicPricingTableLine(TransactionCase):
    """Tests for rental.dynamic.pricing.table.line  [RD02, RD03, RD04]"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.DPTable = cls.env['rental.dynamic.pricing.table']
        cls.DPLine = cls.env['rental.dynamic.pricing.table.line']
        cls.table = cls.DPTable.create({
            'name': 'Constraint Tests',
            'selection_calendar': 'start_hour',
        })

    # -- RD02: factor_percentage > 0 ------------------------------------------

    def test_rd02_normal_factor(self):
        """Factor 120% is accepted."""
        line = self.DPLine.create({
            'table_id': self.table.id,
            'start_datetime': datetime(2026, 7, 1),
            'end_datetime': datetime(2026, 7, 15),
            'factor_percentage': 120.0,
        })
        self.assertEqual(line.factor_percentage, 120.0)

    def test_rd02_factor_below_100(self):
        """Factor 80% (discount) is accepted."""
        line = self.DPLine.create({
            'table_id': self.table.id,
            'start_datetime': datetime(2026, 8, 1),
            'end_datetime': datetime(2026, 8, 15),
            'factor_percentage': 80.0,
        })
        self.assertEqual(line.factor_percentage, 80.0)

    @mute_logger('odoo.sql_db')
    def test_rd02_zero_factor_blocked(self):
        """Factor = 0% is blocked by SQL CHECK."""
        with self.assertRaises(IntegrityError):
            self.DPLine.create({
                'table_id': self.table.id,
                'start_datetime': datetime(2026, 9, 1),
                'end_datetime': datetime(2026, 9, 15),
                'factor_percentage': 0.0,
            })

    @mute_logger('odoo.sql_db')
    def test_rd02_negative_factor_blocked(self):
        """Negative factor is blocked by SQL CHECK."""
        with self.assertRaises(IntegrityError):
            self.DPLine.create({
                'table_id': self.table.id,
                'start_datetime': datetime(2026, 10, 1),
                'end_datetime': datetime(2026, 10, 15),
                'factor_percentage': -10.0,
            })

    # -- RD04: start < end ----------------------------------------------------

    @mute_logger('odoo.sql_db')
    def test_rd04_start_after_end_blocked(self):
        """Start datetime after end datetime is blocked by SQL CHECK."""
        with self.assertRaises(IntegrityError):
            self.DPLine.create({
                'table_id': self.table.id,
                'start_datetime': datetime(2026, 7, 15),
                'end_datetime': datetime(2026, 7, 1),
                'factor_percentage': 100.0,
            })

    @mute_logger('odoo.sql_db')
    def test_rd04_start_equals_end_blocked(self):
        """Start == end is blocked by SQL CHECK (strict inequality)."""
        with self.assertRaises(IntegrityError):
            self.DPLine.create({
                'table_id': self.table.id,
                'start_datetime': datetime(2026, 7, 1),
                'end_datetime': datetime(2026, 7, 1),
                'factor_percentage': 100.0,
            })

    # -- RD03: no overlap within same table -----------------------------------

    def test_rd03_non_overlapping_lines_allowed(self):
        """Adjacent non-overlapping lines are allowed."""
        l1 = self.DPLine.create({
            'table_id': self.table.id,
            'start_datetime': datetime(2026, 6, 1),
            'end_datetime': datetime(2026, 6, 15),
            'factor_percentage': 110.0,
        })
        l2 = self.DPLine.create({
            'table_id': self.table.id,
            'start_datetime': datetime(2026, 6, 15),
            'end_datetime': datetime(2026, 6, 30),
            'factor_percentage': 90.0,
        })
        self.assertTrue(l1.id and l2.id)

    def test_rd03_overlapping_lines_blocked(self):
        """Overlapping lines in the same table are blocked."""
        self.DPLine.create({
            'table_id': self.table.id,
            'start_datetime': datetime(2026, 11, 1),
            'end_datetime': datetime(2026, 11, 20),
            'factor_percentage': 130.0,
        })
        with self.assertRaises(ValidationError):
            self.DPLine.create({
                'table_id': self.table.id,
                'start_datetime': datetime(2026, 11, 15),
                'end_datetime': datetime(2026, 12, 1),
                'factor_percentage': 110.0,
            })

    def test_rd03_fully_contained_overlap_blocked(self):
        """A line fully inside another line is blocked."""
        self.DPLine.create({
            'table_id': self.table.id,
            'start_datetime': datetime(2026, 12, 1),
            'end_datetime': datetime(2026, 12, 31),
            'factor_percentage': 140.0,
        })
        with self.assertRaises(ValidationError):
            self.DPLine.create({
                'table_id': self.table.id,
                'start_datetime': datetime(2026, 12, 10),
                'end_datetime': datetime(2026, 12, 20),
                'factor_percentage': 120.0,
            })

    def test_rd03_same_period_different_table_allowed(self):
        """Same period in different tables is allowed."""
        table2 = self.env['rental.dynamic.pricing.table'].create({
            'name': 'Other Table',
            'selection_calendar': 'start_hour',
        })
        l1 = self.DPLine.create({
            'table_id': self.table.id,
            'start_datetime': datetime(2027, 1, 1),
            'end_datetime': datetime(2027, 1, 31),
            'factor_percentage': 150.0,
        })
        l2 = self.DPLine.create({
            'table_id': table2.id,
            'start_datetime': datetime(2027, 1, 1),
            'end_datetime': datetime(2027, 1, 31),
            'factor_percentage': 120.0,
        })
        self.assertTrue(l1.id and l2.id)


class TestWeightedFactorPercentage(TransactionCase):
    """Tests for get_weighted_factor_percentage()  [RD05, RD06, RD07, RD08, RD09]"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.DPTable = cls.env['rental.dynamic.pricing.table']
        cls.table = cls.DPTable.create({
            'name': 'Weighted Tests',
            'selection_calendar': 'start_hour',
            'line_ids': [
                (0, 0, {
                    'start_datetime': datetime(2026, 7, 1, 0, 0),
                    'end_datetime': datetime(2026, 7, 15, 0, 0),
                    'factor_percentage': 150.0,
                }),
                (0, 0, {
                    'start_datetime': datetime(2026, 8, 1, 0, 0),
                    'end_datetime': datetime(2026, 8, 15, 0, 0),
                    'factor_percentage': 120.0,
                }),
                (0, 0, {
                    'start_datetime': datetime(2026, 9, 1, 0, 0),
                    'end_datetime': datetime(2026, 9, 30, 0, 0),
                    'factor_percentage': 80.0,
                }),
            ],
        })

    # -- RD08: no matching line → 100% ----------------------------------------

    def test_rd08_no_overlap_returns_100(self):
        """Rental period with no overlapping factor lines returns 100%."""
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 6, 1), datetime(2026, 6, 10),
        )
        self.assertEqual(result, 100.0)

    def test_rd08_empty_table_returns_100(self):
        """Table with no lines returns 100%."""
        empty = self.DPTable.create({
            'name': 'Empty',
            'selection_calendar': 'start_hour',
        })
        result = empty.get_weighted_factor_percentage(
            datetime(2026, 7, 1), datetime(2026, 7, 10),
        )
        self.assertEqual(result, 100.0)

    def test_rd08_none_dates_returns_100(self):
        """None start or end datetime returns 100%."""
        self.assertEqual(
            self.table.get_weighted_factor_percentage(None, datetime(2026, 7, 1)),
            100.0,
        )
        self.assertEqual(
            self.table.get_weighted_factor_percentage(datetime(2026, 7, 1), None),
            100.0,
        )

    def test_rd08_start_equals_end_returns_100(self):
        """Zero-length rental period returns 100%."""
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 7, 5), datetime(2026, 7, 5),
        )
        self.assertEqual(result, 100.0)

    def test_rd08_start_after_end_returns_100(self):
        """Inverted dates return 100%."""
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 7, 10), datetime(2026, 7, 1),
        )
        self.assertEqual(result, 100.0)

    # -- RD07: one matching line (fully inside) --------------------------------

    def test_rd07_fully_inside_one_line(self):
        """Rental fully inside a factor line returns that line's factor."""
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 7, 2), datetime(2026, 7, 5),
        )
        self.assertEqual(result, 150.0)

    def test_rd07_exactly_matching_one_line(self):
        """Rental exactly matching a line's boundaries returns its factor."""
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 7, 1), datetime(2026, 7, 15),
        )
        self.assertEqual(result, 150.0)

    def test_rd07_discount_factor_line(self):
        """Rental inside a line with factor < 100 returns that factor."""
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 9, 5), datetime(2026, 9, 20),
        )
        self.assertEqual(result, 80.0)

    # -- RD05/RD06: partial overlap + uncovered gap ----------------------------

    def test_rd05_partial_overlap_single_line(self):
        """Spec example: 10h rental, 4h at 150%, 6h uncovered.
        Weighted: (4*150 + 6*100) / 10 = 120%."""
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 7, 14, 20, 0),  # 4h overlap with Jul line
            datetime(2026, 7, 15, 6, 0),   # 6h uncovered
        )
        self.assertAlmostEqual(result, 120.0, places=4)

    def test_rd05_rental_starts_before_line(self):
        """Rental starts before a line and ends inside it."""
        # Jun 28 → Jul 4 = 6 days total
        # Jun 28 → Jul 1 = 3 days uncovered (100%)
        # Jul 1 → Jul 4 = 3 days at 150%
        # Weighted: (3*100 + 3*150) / 6 = 125%
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 6, 28), datetime(2026, 7, 4),
        )
        self.assertAlmostEqual(result, 125.0, places=4)

    def test_rd05_rental_spans_entire_line_plus_uncovered(self):
        """Rental covers an entire line plus uncovered days."""
        # Jun 25 → Jul 20 = 25 days
        # Jun 25 → Jul 1 = 6 days uncovered (100%)
        # Jul 1 → Jul 15 = 14 days at 150%
        # Jul 15 → Jul 20 = 5 days uncovered (100%)
        # Weighted: (6*100 + 14*150 + 5*100) / 25 = (600+2100+500)/25 = 128%
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 6, 25), datetime(2026, 7, 20),
        )
        self.assertAlmostEqual(result, 128.0, places=4)

    # -- RD05: multiple matching lines -----------------------------------------

    def test_rd05_multiple_lines_with_gap(self):
        """Rental spanning two factor lines with a gap between them.
        Jul 10 → Aug 10 = 31 days:
          Jul 10–15 = 5 days at 150%
          Jul 15–Aug 1 = 17 days uncovered (100%)
          Aug 1–10 = 9 days at 120%
        Weighted: (5*150 + 17*100 + 9*120) / 31 = 3530/31 ≈ 113.87%"""
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 7, 10), datetime(2026, 8, 10),
        )
        expected = (5 * 150 + 17 * 100 + 9 * 120) / 31.0
        self.assertAlmostEqual(result, expected, places=2)

    def test_rd05_three_lines_covered(self):
        """Rental spanning all three factor lines.
        Jul 1 → Sep 30 = 91 days:
          Jul 1–15 = 14 days at 150%
          Jul 15–Aug 1 = 17 days uncovered (100%)
          Aug 1–15 = 14 days at 120%
          Aug 15–Sep 1 = 17 days uncovered (100%)
          Sep 1–30 = 29 days at 80%
        Weighted: (14*150 + 17*100 + 14*120 + 17*100 + 29*80) / 91"""
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 7, 1), datetime(2026, 9, 30),
        )
        expected = (14 * 150 + 17 * 100 + 14 * 120 + 17 * 100 + 29 * 80) / 91.0
        self.assertAlmostEqual(result, expected, places=2)

    # -- RD09: dynamic multiplier = factor_percentage / 100 --------------------

    def test_rd09_multiplier_calculation(self):
        """Dynamic multiplier is factor_percentage / 100."""
        pct = self.table.get_weighted_factor_percentage(
            datetime(2026, 7, 2), datetime(2026, 7, 5),
        )
        multiplier = pct / 100.0
        self.assertAlmostEqual(multiplier, 1.5)

    def test_rd09_multiplier_no_change(self):
        """Factor 100% gives multiplier 1.0 (no price change)."""
        pct = self.table.get_weighted_factor_percentage(
            datetime(2026, 6, 1), datetime(2026, 6, 10),
        )
        self.assertAlmostEqual(pct / 100.0, 1.0)

    def test_rd09_multiplier_discount(self):
        """Factor 80% gives multiplier 0.8 (20% discount)."""
        pct = self.table.get_weighted_factor_percentage(
            datetime(2026, 9, 5), datetime(2026, 9, 20),
        )
        self.assertAlmostEqual(pct / 100.0, 0.8)

    # -- Edge cases ------------------------------------------------------------

    def test_edge_very_short_overlap(self):
        """1-second overlap at the boundary of a factor line."""
        # Jul 14, 23:59:59 → Jul 15, 00:00:01 = 2 seconds total
        # 1 second in Jul line at 150%, 1 second uncovered at 100%
        # Weighted: (1*150 + 1*100) / 2 = 125%
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 7, 14, 23, 59, 59),
            datetime(2026, 7, 15, 0, 0, 1),
        )
        self.assertAlmostEqual(result, 125.0, places=2)

    def test_edge_rental_between_lines_no_overlap(self):
        """Rental falls in a gap between two lines → 100%."""
        result = self.table.get_weighted_factor_percentage(
            datetime(2026, 7, 20), datetime(2026, 7, 25),
        )
        self.assertEqual(result, 100.0)

    def test_edge_adjacent_lines_continuous_coverage(self):
        """Two adjacent lines that together cover the full rental."""
        table = self.DPTable.create({
            'name': 'Adjacent',
            'selection_calendar': 'start_hour',
            'line_ids': [
                (0, 0, {
                    'start_datetime': datetime(2026, 7, 1),
                    'end_datetime': datetime(2026, 7, 10),
                    'factor_percentage': 150.0,
                }),
                (0, 0, {
                    'start_datetime': datetime(2026, 7, 10),
                    'end_datetime': datetime(2026, 7, 20),
                    'factor_percentage': 80.0,
                }),
            ],
        })
        # Jul 1 → Jul 20 = 19 days. 9 days at 150%, 10 days at 80%
        # Weighted: (9*150 + 10*80) / 19 = (1350+800)/19 ≈ 113.16%
        result = table.get_weighted_factor_percentage(
            datetime(2026, 7, 1), datetime(2026, 7, 20),
        )
        expected = (9 * 150 + 10 * 80) / 19.0
        self.assertAlmostEqual(result, expected, places=2)

    def test_edge_hour_granularity_precision(self):
        """Weighted factor with sub-day precision (hours).
        Rental: 24 hours. 8h at 200%, 16h uncovered (100%).
        Weighted: (8*200 + 16*100) / 24 = (1600+1600)/24 ≈ 133.33%"""
        table = self.DPTable.create({
            'name': 'Hourly Precision',
            'selection_calendar': 'start_hour',
            'line_ids': [
                (0, 0, {
                    'start_datetime': datetime(2026, 7, 1, 8, 0),
                    'end_datetime': datetime(2026, 7, 1, 16, 0),
                    'factor_percentage': 200.0,
                }),
            ],
        })
        result = table.get_weighted_factor_percentage(
            datetime(2026, 7, 1, 0, 0),
            datetime(2026, 7, 2, 0, 0),
        )
        expected = (8 * 200 + 16 * 100) / 24.0
        self.assertAlmostEqual(result, expected, places=2)
