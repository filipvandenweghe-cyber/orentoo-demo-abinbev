# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _check_availability(self):
        """Override to check component availability for rental set lines.

        The set parent product has no stock of its own, so the standard
        check (which looks at product.free_qty) would either always pass
        (not storable) or always fail (zero stock).  Instead we delegate
        to the set-aware ``_get_cart_and_free_qty`` on the order, which
        evaluates leaf component stock.
        """
        self.ensure_one()
        tmpl = self.product_id.product_tmpl_id
        if tmpl.is_rental_set and not tmpl.allow_out_of_stock_order:
            cart_qty, avl_qty = self.order_id._get_cart_and_free_qty(
                self.product_id,
            )
            if cart_qty > avl_qty:
                self._set_shop_warning_stock(cart_qty, max(avl_qty, 0))
                return False
            return True
        return super()._check_availability()

    def _set_shop_warning_stock(self, desired_qty, new_qty, save=True):
        """Override to provide a set-specific warning message."""
        self.ensure_one()
        tmpl = self.product_id.product_tmpl_id
        if not tmpl.is_rental_set:
            return super()._set_shop_warning_stock(
                desired_qty, new_qty, save=save,
            )

        if self.is_rental:
            warning = _(
                "You asked for %(desired_qty)s %(product_name)s but only"
                " %(new_qty)s complete sets are available from"
                " %(rental_period)s.",
                desired_qty=desired_qty,
                product_name=self.product_id.name,
                new_qty=new_qty,
                rental_period=self._get_rental_order_line_description(),
            )
        else:
            warning = _(
                "You asked for %(desired_qty)s %(product_name)s but only"
                " %(new_qty)s complete sets are available.",
                desired_qty=desired_qty,
                product_name=self.product_id.name,
                new_qty=new_qty,
            )

        if save:
            self.shop_warning = warning
        return warning
