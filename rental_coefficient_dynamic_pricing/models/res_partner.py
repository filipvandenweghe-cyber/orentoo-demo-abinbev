from odoo import fields, models


class ResPartner(models.Model):
    """Extend res.partner with allowed coefficient tables.  [RP08, RP09, RP10]"""

    _inherit = 'res.partner'

    use_dynamic_pricing = fields.Boolean(  # RP10
        string='Dynamic Pricing',
        default=True,
        help=(
            'When enabled, dynamic pricing factors (seasonal, peak, etc.) '
            'are applied to rental prices for this customer. '
            'When disabled, the dynamic pricing factor is always 100%.'
        ),
    )
    allowed_coefficient_table_ids = fields.Many2many(
        'rental.coefficient.table',
        relation='res_partner_coeff_table_rel',
        column1='partner_id',
        column2='table_id',
        string='Allowed Coefficient Tables',
        help=(
            'Coefficient tables that may be used when computing rental prices '
            'for this customer. Leave empty to use the standard defaults.'
        ),
    )

    # -------------------------------------------------------------------------
    # Helper  [RP09]
    # -------------------------------------------------------------------------

    def _get_customer_allowed_coefficient_tables(self, company=None):
        """Return the customer's allowed coefficient tables, optionally
        filtered by company.

        :param res.company company: if given, only return tables belonging
            to this company.
        :returns: ``rental.coefficient.table`` recordset (may be empty).
        """
        self.ensure_one()
        tables = self.allowed_coefficient_table_ids
        if company:
            tables = tables.filtered(lambda t: t.company_id == company)
        return tables
