from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_rental_set = fields.Boolean(
        string='Is a Rental Set',
        help=(
            'When enabled, this product acts as a Rental Set \u2014 a normal '
            'Odoo product that expands into hidden internal components for '
            'rental, sales, inventory and warehouse operations.'
        ),
    )
    set_pricing_mode = fields.Selection(
        selection=[
            ('fixed', 'Fixed Price'),
            ('sum', 'Sum of Components'),
        ],
        string='Set Pricing Mode',
        default='fixed',
        help=(
            'Fixed Price: the set price is defined directly on this product.\n'
            'Sum of Components: the set price is computed from the sum of its '
            'component prices.'
        ),
    )
    set_component_ids = fields.One2many(
        comodel_name='rental.set.component',
        inverse_name='set_product_tmpl_id',
        string='Set Components',
    )
    set_availability = fields.Float(
        string='Set Availability',
        compute='_compute_set_availability',
        digits='Product Unit of Measure',
        help=(
            'How many complete Rental Sets can be assembled right now from '
            'current stock.  Equals the minimum of '
            'on_hand(component) / qty_per_set across all components.'
        ),
    )

    set_website_description = fields.Html(
        string='Set Contents Description',
        compute='_compute_set_website_description',
        store=True,
        readonly=False,
        help=(
            'Auto-generated HTML description listing the set contents '
            '(component names and quantities).  Editable \u2014 manual changes '
            'are preserved until components are modified.'
        ),
    )

    @api.depends(
        'is_rental_set',
        'set_component_ids.product_id',
        'set_component_ids.quantity',
    )
    def _compute_set_availability(self):
        """Compute how many complete sets can be assembled from current stock.

        Flattens the entire component hierarchy (including nested sets) to
        evaluate availability based on **all** leaf products, each with its
        cumulative quantity per one unit of the top-level set.
        """
        for tmpl in self:
            if not tmpl.is_rental_set or not tmpl.set_component_ids:
                tmpl.set_availability = 0.0
                continue

            leaves = []
            self._collect_leaf_components_for_availability(tmpl, 1.0, leaves)

            if not leaves:
                tmpl.set_availability = 0.0
                continue

            # Group by product: sum cumulative quantities so the same product
            # appearing in multiple branches correctly reflects total demand.
            product_demand = {}
            for product, cumulative_qty in leaves:
                pid = product.id
                if pid not in product_demand:
                    product_demand[pid] = {'product': product, 'total_qty': 0.0}
                product_demand[pid]['total_qty'] += cumulative_qty

            min_sets = float('inf')
            for data in product_demand.values():
                on_hand = data['product'].qty_available
                sets_possible = on_hand / data['total_qty'] if data['total_qty'] else 0.0
                min_sets = min(min_sets, sets_possible)

            tmpl.set_availability = max(min_sets, 0.0) if min_sets != float('inf') else 0.0

    @api.model
    def _collect_leaf_components_for_availability(self, tmpl, parent_multiplier, result):
        """Recursively collect all leaf component products under ``tmpl``.

        Each entry in ``result`` is a tuple ``(product, cumulative_qty)``
        where ``cumulative_qty`` is the total quantity of this product needed
        per 1 unit of the **top-level** set (product of all component
        quantities along the path).

        Nested sets are traversed transparently — only actual leaf products
        end up in the result list.
        """
        for comp in tmpl.set_component_ids:
            if not comp.product_id or not comp.quantity:
                continue
            cumulative = parent_multiplier * comp.quantity
            comp_tmpl = comp.product_id.product_tmpl_id
            if comp_tmpl.is_rental_set and comp_tmpl.set_component_ids:
                # Nested set: recurse deeper
                self._collect_leaf_components_for_availability(comp_tmpl, cumulative, result)
            else:
                # Leaf component
                result.append((comp.product_id, cumulative))

    @api.depends(
        'is_rental_set',
        'set_component_ids.product_id',
        'set_component_ids.product_id.name',
        'set_component_ids.quantity',
    )
    def _compute_set_website_description(self):
        """Generate an HTML description listing the set contents.

        Produces a clean list like:
            This set includes:
            - 1 x Tent
            - 4 x Chair
            - 2 x Table

        Each component's sale description is appended if available.
        """
        for tmpl in self:
            if not tmpl.is_rental_set or not tmpl.set_component_ids:
                tmpl.set_website_description = ''
                continue

            lines = []
            for comp in tmpl.set_component_ids.sorted('sequence'):
                if not comp.product_id:
                    continue
                qty = int(comp.quantity) if comp.quantity == int(comp.quantity) else comp.quantity
                name = comp.product_id.display_name
                desc = comp.product_id.description_sale
                line = f'<li><strong>{qty} x {name}</strong>'
                if desc:
                    line += f'<br/><span style="color: #666;">{desc}</span>'
                line += '</li>'
                lines.append(line)

            if lines:
                tmpl.set_website_description = (
                    '<p>This set includes:</p>'
                    '<ul>' + ''.join(lines) + '</ul>'
                )
            else:
                tmpl.set_website_description = ''

    def _get_set_description_sale(self):
        """Return a plain-text description of set contents for sale order lines.

        Used as the default description_sale when the set is added to an order.
        """
        self.ensure_one()
        if not self.is_rental_set or not self.set_component_ids:
            return ''
        lines = []
        for comp in self.set_component_ids.sorted('sequence'):
            if not comp.product_id:
                continue
            qty = int(comp.quantity) if comp.quantity == int(comp.quantity) else comp.quantity
            lines.append(f'  - {qty} x {comp.product_id.display_name}')
        if lines:
            return 'Includes:\n' + '\n'.join(lines)
        return ''
