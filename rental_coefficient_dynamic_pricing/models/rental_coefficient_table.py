from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RentalCoefficientTable(models.Model):
    """Duration-based degressive pricing coefficients.  [RC04, RC05, RC09, RC10]"""

    _name = 'rental.coefficient.table'
    _description = 'Rental Coefficient Table'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    coefficient_type_id = fields.Many2one(
        'rental.coefficient.type',
        string='Coefficient Type',
        required=True,
        ondelete='restrict',
    )
    sequence = fields.Integer(default=10)
    is_standard = fields.Boolean(
        string='Standard',
        default=False,
        help='Default coefficient table for this company and coefficient type.',
    )
    duration_unit = fields.Selection(
        selection=[
            ('minute', 'Minute'),
            ('hour', 'Hour'),
            ('day', 'Day'),
            ('week', 'Week'),
            ('month', 'Month'),
        ],
        required=True,
        default='day',
    )
    line_ids = fields.One2many(
        'rental.coefficient.table.line',
        'table_id',
        string='Coefficient Lines',
        copy=True,
    )

    @api.constrains('is_standard', 'company_id', 'coefficient_type_id')
    def _check_unique_standard_per_company_type(self):  # RC10
        for table in self.filtered('is_standard'):
            domain = [
                ('is_standard', '=', True),
                ('company_id', '=', table.company_id.id),
                ('coefficient_type_id', '=', table.coefficient_type_id.id),
                ('id', '!=', table.id),
            ]
            if self.search_count(domain):
                raise ValidationError(_(
                    "There can only be one standard coefficient table per company "
                    "and coefficient type. A standard table already exists for "
                    "company '%(company)s' with type '%(type)s'.",
                    company=table.company_id.name,
                    type=table.coefficient_type_id.name,
                ))

    # -------------------------------------------------------------------------
    # Business methods
    # -------------------------------------------------------------------------

    def get_coefficient_for_duration(self, duration_int):  # RC09
        """Return the coefficient for the given duration.

        Selects the coefficient line where ``as_from_duration`` is the highest
        value that does not exceed *duration_int*.

        :param int duration_int: rental duration expressed in the table's
            ``duration_unit``.
        :returns: the matching coefficient (float) or ``False`` when no
            applicable line is found.
        """
        self.ensure_one()
        if duration_int < 0:
            return False
        line = self.line_ids.filtered(
            lambda l: l.as_from_duration <= duration_int
        ).sorted('as_from_duration', reverse=True)[:1]
        return line.coefficient if line else False
