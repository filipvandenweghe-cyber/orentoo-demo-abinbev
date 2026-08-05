# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from datetime import timedelta

from odoo import models
from odoo.http import request


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _get_set_availabilities(self, from_date, to_date, warehouse_id,
                                with_cart=False):
        """Return availability windows for a rental set product.

        Instead of checking the set parent's own stock (which is zero), we
        collect all leaf component products, compute their individual
        availability timelines, and return the *minimum* across all leaves
        at each point in time.

        The result format matches ``_get_availabilities()`` so the frontend
        calendar widget can consume it unchanged.
        """
        self.ensure_one()
        tmpl = self.product_tmpl_id
        if not tmpl.is_rental_set or not tmpl.set_component_ids:
            return []

        # Collect leaf components with cumulative qty per 1 set
        leaves = []
        self.env['product.template']._collect_leaf_components_for_availability(
            tmpl, 1.0, leaves,
        )
        if not leaves:
            return []

        # Group by product, summing cumulative quantities
        product_demand = {}  # product_id -> {product, total_qty}
        for product, cumulative_qty in leaves:
            pid = product.id
            if pid not in product_demand:
                product_demand[pid] = {
                    'product': product,
                    'total_qty': 0.0,
                }
            product_demand[pid]['total_qty'] += cumulative_qty

        if not product_demand:
            return []

        # Compute per-component availability windows
        component_availabilities = []
        for data in product_demand.values():
            product = data['product']
            total_qty = data['total_qty']
            if not product.is_storable or not total_qty:
                continue

            # Get the raw availability windows for this component
            avails = product._get_availabilities(
                from_date, to_date, warehouse_id, with_cart=with_cart,
            )
            # Convert to "how many complete sets" this component can support
            set_avails = []
            for window in avails:
                set_avails.append({
                    'start': window['start'],
                    'end': window['end'],
                    'quantity_available': window['quantity_available'] / total_qty,
                })
            component_availabilities.append(set_avails)

        if not component_availabilities:
            return []

        # Merge all component timelines: at each time window the set
        # availability is the minimum across all components.
        return self._merge_set_availability_windows(component_availabilities)

    def _merge_set_availability_windows(self, component_availabilities):
        """Merge multiple component availability timelines into one.

        At each point in time the set availability equals the minimum
        across all components (the bottleneck determines how many complete
        sets can be rented).

        Strategy: collect all boundary dates, split into micro-windows, and
        for each micro-window take the minimum quantity from every component
        that covers it.
        """
        if len(component_availabilities) == 1:
            # Fast path: single component, floor the quantities
            return [
                {**w, 'quantity_available': max(int(w['quantity_available']), 0)}
                for w in component_availabilities[0]
            ]

        # Collect all unique boundary dates
        boundaries = set()
        for avails in component_availabilities:
            for w in avails:
                boundaries.add(w['start'])
                boundaries.add(w['end'])
        boundaries = sorted(boundaries)

        if len(boundaries) < 2:
            return []

        # Build index: for each component, map start→window for fast lookup
        comp_indexes = []
        for avails in component_availabilities:
            idx = {}
            for w in avails:
                idx[w['start']] = w
            comp_indexes.append(idx)

        # Walk each micro-window
        result = []
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i + 1]

            # Find the minimum set-qty across all components that cover
            # this micro-window.
            min_qty = float('inf')
            for comp_idx, avails in zip(comp_indexes, component_availabilities):
                # Find which window in this component covers [start, end)
                qty = 0.0
                for w in avails:
                    if w['start'] <= start and w['end'] >= end:
                        qty = w['quantity_available']
                        break
                min_qty = min(min_qty, qty)

            if min_qty == float('inf'):
                min_qty = 0.0

            result.append({
                'start': start,
                'end': end,
                'quantity_available': max(int(min_qty), 0),
            })

        return result
