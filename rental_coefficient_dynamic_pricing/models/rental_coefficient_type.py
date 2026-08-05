from odoo import fields, models


class RentalCoefficientType(models.Model):
    """Categorises coefficient tables.  [RC01, RC02, RC03]"""

    _name = 'rental.coefficient.type'
    _description = 'Rental Coefficient Type'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
    )

    # RC03: unique name per company
    _name_company_uniq = models.Constraint(
        'UNIQUE(name, company_id)',
        'A coefficient type with this name already exists for this company.',
    )
