from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rental_show_stock_locations = fields.Boolean(
        related='company_id.rental_show_stock_locations',
        readonly=False,
        string="Show physical stock & locations in availability pop-up",
    )
