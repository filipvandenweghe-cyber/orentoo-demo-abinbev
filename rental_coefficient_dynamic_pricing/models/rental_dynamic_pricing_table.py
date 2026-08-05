from odoo import fields, models


class RentalDynamicPricingTable(models.Model):
    """Time-ranged pricing factor table.  [RD01, RD07, RD08, RD10]"""

    _name = 'rental.dynamic.pricing.table'
    _description = 'Dynamic Pricing Factor Table'
    _order = 'name, id'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    selection_calendar = fields.Selection(
        selection=[
            ('start_hour', 'Start Hour'),
            ('start_day', 'Start Day'),
        ],
        string='Granularity',
        required=True,
        default='start_hour',
        help=(
            'Determines the time granularity for weighted factor computation. '
            '"Start Hour" weighs by hours, "Start Day" weighs by days.'
        ),
    )
    line_ids = fields.One2many(
        'rental.dynamic.pricing.table.line',
        'table_id',
        string='Factor Lines',
        copy=True,
    )

    # -------------------------------------------------------------------------
    # Business methods
    # -------------------------------------------------------------------------

    def get_weighted_factor_percentage(self, start_dt, end_dt):  # RD05, RD06, RD07, RD08
        """Return the weighted average factor percentage for a rental period.

        Compares the rental period [start_dt, end_dt) against the table's
        factor lines.  Parts of the rental period that are not covered by any
        line default to 100 %.

        The weighting granularity depends on ``selection_calendar``:
        * ``start_hour``  – weight by total seconds of overlap
        * ``start_day``   – weight by total seconds of overlap

        Both use seconds internally so the result is identical; the selection
        field is reserved for future calendar-aware rounding.

        :param datetime start_dt: rental start (tz-aware or naive).
        :param datetime end_dt:   rental end   (tz-aware or naive).
        :returns: weighted average factor percentage (float, e.g. 120.0).
                  Returns 100.0 when no factor line applies.
        """
        self.ensure_one()
        if not start_dt or not end_dt or start_dt >= end_dt:
            return 100.0

        total_seconds = (end_dt - start_dt).total_seconds()
        if total_seconds <= 0:
            return 100.0

        covered_seconds = 0.0
        weighted_sum = 0.0

        for line in self.line_ids.sorted('start_datetime'):
            # Compute overlap between rental period and factor line
            overlap_start = max(start_dt, line.start_datetime)
            overlap_end = min(end_dt, line.end_datetime)
            overlap = (overlap_end - overlap_start).total_seconds()
            if overlap <= 0:
                continue
            covered_seconds += overlap
            weighted_sum += overlap * line.factor_percentage

        # Uncovered part defaults to 100 %
        uncovered_seconds = total_seconds - covered_seconds
        weighted_sum += uncovered_seconds * 100.0

        return weighted_sum / total_seconds
