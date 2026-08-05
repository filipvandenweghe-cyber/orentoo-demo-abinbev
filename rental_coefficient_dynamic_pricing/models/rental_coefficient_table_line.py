from odoo import api, fields, models


class RentalCoefficientTableLine(models.Model):
    """Single threshold → coefficient mapping inside a table.  [RC06, RC07, RC08]"""

    _name = 'rental.coefficient.table.line'
    _description = 'Rental Coefficient Table Line'
    _order = 'as_from_duration, id'

    table_id = fields.Many2one(
        'rental.coefficient.table',
        required=True,
        ondelete='cascade',
        index=True,
    )
    as_from_duration = fields.Integer(
        string='As From Duration',
        required=True,
        help='Minimum duration (inclusive) for this coefficient to apply.',
    )
    coefficient = fields.Float(
        required=True,
        digits=(12, 4),
        default=1.0,
    )
    sequence = fields.Integer(
        compute='_compute_sequence',
        store=True,
    )

    _non_negative_duration = models.Constraint(  # RC06
        'CHECK(as_from_duration >= 0)',
        'Duration must be zero or a positive integer.',
    )
    _positive_coefficient = models.Constraint(  # RC06
        'CHECK(coefficient > 0)',
        'Coefficient must be positive.',
    )
    _unique_duration_per_table = models.Constraint(  # RC07
        'UNIQUE(table_id, as_from_duration)',
        'Duplicate duration value within the same coefficient table.',
    )

    @api.depends('as_from_duration')
    def _compute_sequence(self):  # RC08
        for line in self:
            line.sequence = line.as_from_duration
