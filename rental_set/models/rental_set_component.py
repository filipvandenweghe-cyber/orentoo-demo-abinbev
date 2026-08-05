from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class RentalSetComponent(models.Model):
    _name = 'rental.set.component'
    _description = 'Rental Set Component'
    _order = 'sequence, id'

    set_product_tmpl_id = fields.Many2one(
        comodel_name='product.template',
        string='Rental Set',
        required=True,
        ondelete='cascade',
        index=True,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Component Product',
        required=True,
        index=True,
    )
    quantity = fields.Float(
        string='Quantity',
        default=1.0,
        digits='Product Unit of Measure',
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

    # Self-referential hierarchy (for nested component groups)
    parent_component_id = fields.Many2one(
        comodel_name='rental.set.component',
        string='Parent Component',
        ondelete='cascade',
        index=True,
    )
    child_component_ids = fields.One2many(
        comodel_name='rental.set.component',
        inverse_name='parent_component_id',
        string='Child Components',
    )

    # ── Constraints ───────────────────────────────────────────────────────────

    @api.constrains('product_id')
    def _check_no_optional_products(self):
        """Optional products must not be configured on component products.

        Optional, alternative, and accessory product recommendations belong
        on the parent set level, not on individual components.  Components
        are expanded automatically and should never trigger the product
        configurator.
        """
        for record in self:
            tmpl = record.product_id.product_tmpl_id
            if tmpl.optional_product_ids:
                raise ValidationError(_(
                    "Component '%(comp)s' has optional products configured. "
                    "Optional products should be set on the parent Rental Set, "
                    "not on individual components.",
                    comp=tmpl.display_name,
                ))

    @api.constrains('set_product_tmpl_id', 'product_id')
    def _check_no_circular_reference(self):
        """Prevent a Rental Set from containing itself (directly or indirectly)
        as a component.

        Walks the full component graph of the new component product and raises a
        ValidationError if the owning set template appears anywhere in the tree.
        """
        for record in self:
            comp_tmpl = record.product_id.product_tmpl_id
            if not comp_tmpl.is_rental_set:
                continue
            if self._component_graph_contains(
                root_tmpl=comp_tmpl,
                target_id=record.set_product_tmpl_id.id,
                visited=set(),
            ):
                raise ValidationError(_(
                    "Circular reference: adding '%(component)s' as a component "
                    "of '%(set)s' would create an infinite loop in the Rental "
                    "Set structure.",
                    component=comp_tmpl.display_name,
                    set=record.set_product_tmpl_id.display_name,
                ))

    @api.model
    def _component_graph_contains(self, root_tmpl, target_id, visited):
        """Return True if ``target_id`` (a product.template id) appears anywhere
        in the component tree rooted at ``root_tmpl``.

        Uses an explicit ``visited`` set to handle shared sub-trees without
        infinite loops.
        """
        if root_tmpl.id in visited:
            return False
        visited.add(root_tmpl.id)

        for comp in root_tmpl.set_component_ids:
            child_tmpl = comp.product_id.product_tmpl_id
            if child_tmpl.id == target_id:
                return True
            if child_tmpl.is_rental_set and self._component_graph_contains(
                root_tmpl=child_tmpl,
                target_id=target_id,
                visited=visited,
            ):
                return True
        return False
