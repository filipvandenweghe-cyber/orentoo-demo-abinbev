from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    rental_show_stock_locations = fields.Boolean(
        string="Show physical stock & locations in availability pop-up",
        default=False,
        help="Show the 'Physical stock (right now)' section — total stock and "
             "its locations — in the rental availability pop-up.  Off by "
             "default to keep the pop-up light; handy for troubleshooting.",
    )
