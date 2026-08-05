# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo.http import request, route

from odoo.addons.website_sale_stock_renting.controllers.main import (
    WebsiteSaleStockRenting,
)


class WebsiteSaleStockRentingSet(WebsiteSaleStockRenting):

    @route()
    def renting_product_availabilities(self, product_id, min_date, max_date):
        """Override to compute availability from set components.

        For rental set products the standard per-product availability is
        meaningless because the set parent carries no stock of its own.
        Instead we compute component-based availability windows so that the
        frontend calendar correctly reflects which dates are bookable.
        """
        result = super().renting_product_availabilities(
            product_id, min_date, max_date,
        )

        product_sudo = (
            request.env['product.product'].sudo().browse(product_id).exists()
        )
        if not product_sudo:
            return result

        tmpl = product_sudo.product_tmpl_id
        if not tmpl.is_rental_set or tmpl.allow_out_of_stock_order:
            return result

        # Compute set-level availability from leaf components
        from_dt = fields.Datetime.to_datetime(min_date)
        to_dt = fields.Datetime.to_datetime(max_date)
        warehouse_id = request.website.warehouse_id.id

        result['renting_availabilities'] = (
            product_sudo._get_set_availabilities(from_dt, to_dt, warehouse_id)
        )

        return result
