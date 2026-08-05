from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RentalDynamicPricingTableLine(models.Model):
    """Single date-range factor line inside a dynamic pricing table.  [RD02, RD03, RD04]"""

    _name = 'rental.dynamic.pricing.table.line'
    _description = 'Dynamic Pricing Factor Table Line'
    _order = 'start_datetime, id'

    table_id = fields.Many2one(
        'rental.dynamic.pricing.table',
        required=True,
        ondelete='cascade',
        index=True,
    )
    start_datetime = fields.Datetime(
        string='Start',
        required=True,
    )
    end_datetime = fields.Datetime(
        string='End',
        required=True,
    )
    factor_percentage = fields.Float(
        string='Factor (%)',
        required=True,
        default=100.0,
        help=(
            'Pricing factor as a percentage. '
            '100 = no change, 120 = +20%, 80 = -20%.'
        ),
    )

    _positive_factor = models.Constraint(  # RD02
        'CHECK(factor_percentage > 0)',
        'Factor percentage must be positive.',
    )
    _start_before_end = models.Constraint(  # RD04
        'CHECK(start_datetime < end_datetime)',
        'Start date/time must be before end date/time.',
    )

    @api.constrains('table_id', 'start_datetime', 'end_datetime')
    def _check_no_overlap(self):  # RD03
        for line in self:
            domain = [
                ('table_id', '=', line.table_id.id),
                ('id', '!=', line.id),
                ('start_datetime', '<', line.end_datetime),
                ('end_datetime', '>', line.start_datetime),
            ]
            if self.search_count(domain):
                raise ValidationError(_(
                    "Dynamic pricing lines in the same table may not overlap. "
                    "Line '%(start)s – %(end)s' overlaps with an existing line.",
                    start=line.start_datetime,
                    end=line.end_datetime,
                ))
