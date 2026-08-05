from odoo import fields, models

# Business requirements: PF09, PR07


class RentalFlowDurationOption(models.Model):
    """Fallback duration option when no coefficient table applies.  [PF09]"""

    _name = 'multi.channel.rental.duration.option'
    _description = 'Fallback Duration Option'
    _order = 'sequence, id'

    profile_id = fields.Many2one(
        'multi.channel.rental.profile',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(
        required=True,
        translate=True,
        help="Display label shown to the customer, e.g. '1 hour', 'Half day'.",
    )
    duration_value = fields.Integer(
        required=True,
        default=1,
        help="Number of duration units.",
    )
    duration_unit = fields.Selection(
        selection=[
            ('minute', "Minutes"),
            ('hour', "Hours"),
            ('day', "Days"),
            ('week', "Weeks"),
            ('month', "Months"),
        ],
        required=True,
        default='hour',
    )
    sequence = fields.Integer(default=10)
