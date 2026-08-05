from odoo import api, models


class SaleOrder(models.Model):
    """Extend sale.order for coefficient & dynamic pricing triggers.  [RI05]"""

    _inherit = 'sale.order'

    @api.onchange('partner_id')
    def _onchange_partner_show_update_rental_prices(self):  # RI05
        """Show the 'Update Rental Prices' button when the customer changes.

        Changing the customer may affect which coefficient table is
        selected (customer-allowed tables) and whether dynamic pricing
        is active for this customer.
        """
        if any(line.is_rental for line in self.order_line):
            self.show_update_duration = True
