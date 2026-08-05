# Part of Odoo. See LICENSE file for full copyright and licensing details.

from math import floor

from odoo import models
from odoo.http import request


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _get_additionnal_combination_info(self, product_or_template, quantity,
                                           uom, date, website):
        """Override to provide component-based free_qty for rental sets.

        The standard method returns free_qty from the parent product
        (which is 0 for sets — they carry no stock).  The JS variant
        mixin hides the Add-to-Cart button when free_qty < 1.

        For rental sets we compute free_qty from the minimum component
        availability so the button is correctly enabled.
        """
        res = super()._get_additionnal_combination_info(
            product_or_template, quantity, uom, date, website,
        )

        tmpl = (
            product_or_template.product_tmpl_id
            if product_or_template.is_product_variant
            else product_or_template
        )
        if not tmpl.is_rental_set or tmpl.allow_out_of_stock_order:
            return res

        variant = (
            product_or_template
            if product_or_template.is_product_variant
            else tmpl.product_variant_id
        )
        if not variant:
            return res

        start_date = self.env.context.get('start_date')
        end_date = self.env.context.get('end_date')
        warehouse_id = website.warehouse_id.id if website else False

        if start_date and end_date and warehouse_id:
            avails = variant.sudo()._get_set_availabilities(
                start_date, end_date, warehouse_id,
            )
            set_qty = max(
                (w['quantity_available'] for w in avails), default=0,
            )
        else:
            set_qty = self._get_set_free_qty(variant, warehouse_id)

        res['free_qty'] = floor(set_qty)
        return res

    def _get_set_free_qty(self, variant, warehouse_id):
        """Compute available complete sets from component on-hand stock.

        Uses sudo() because this may be called from the website context
        where public/portal users lack product.product read access.
        """
        tmpl_sudo = variant.sudo().product_tmpl_id
        if not tmpl_sudo.set_component_ids:
            return 0

        min_sets = float('inf')
        for comp in tmpl_sudo.set_component_ids:
            product = comp.product_id
            if not product.is_storable or not comp.quantity:
                continue
            qty = product.with_context(
                warehouse_id=warehouse_id,
            ).free_qty if warehouse_id else product.free_qty
            sets_possible = qty / comp.quantity
            min_sets = min(min_sets, sets_possible)

        return max(min_sets if min_sets != float('inf') else 0, 0)

    def _is_sold_out(self):
        """Override to check component availability for rental sets."""
        if self.is_rental_set and not self.allow_out_of_stock_order:
            tmpl_sudo = self.sudo()
            start_date = self.env.context.get('start_date')
            end_date = self.env.context.get('end_date')
            warehouse_id = (
                request.website.warehouse_id.id if request else False
            )
            if start_date and end_date:
                for variant in tmpl_sudo.product_variant_ids:
                    avails = variant._get_set_availabilities(
                        start_date, end_date, warehouse_id,
                    )
                    if any(w['quantity_available'] > 0 for w in avails):
                        return False
                return True
            return self._get_set_free_qty(
                tmpl_sudo.product_variant_id, warehouse_id,
            ) <= 0
        return super()._is_sold_out()

    def _filter_on_available_rental_products(self, from_date, to_date,
                                              warehouse_id):
        """Override to include rental sets based on component availability."""
        available = super()._filter_on_available_rental_products(
            from_date, to_date, warehouse_id,
        )

        excluded_sets = (self - available).sudo().filtered(
            lambda t: t.is_rental_set
                      and not t.allow_out_of_stock_order
                      and t.set_component_ids
        )
        for tmpl in excluded_sets:
            for variant in tmpl.product_variant_ids:
                avails = variant._get_set_availabilities(
                    from_date, to_date, warehouse_id,
                )
                if any(w['quantity_available'] > 0 for w in avails):
                    available |= tmpl
                    break

        return available
