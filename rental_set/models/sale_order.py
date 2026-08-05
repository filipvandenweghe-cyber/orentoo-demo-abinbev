from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def copy(self, default=None):
        """Skip set expansion when duplicating an order.

        When an order with a rental set is duplicated, Odoo copies both
        the set parent line and all its component lines.  Without the
        rental_set_copying flag, create() would call _expand_rental_set()
        on the copied parent, creating a second set of components.

        After copying, we remap set_parent_line_id on the new order's
        component lines so they reference the new parent (not the
        original order's parent line).  (RS11)
        """
        self = self.with_context(rental_set_copying=True)
        new_order = super(SaleOrder, self).copy(default=default)

        # Remap set_parent_line_id: find new parents by matching product
        # and is_set flag, then link children to them.
        old_lines = self.order_line
        new_lines = new_order.order_line

        # Build mapping: old_parent_id → new_parent_line
        parent_map = {}
        for old_line in old_lines.filtered(lambda l: l.is_set and not l.is_set_component):
            # Find matching new parent by product and sequence
            new_parent = new_lines.filtered(
                lambda l: (
                    l.is_set and not l.is_set_component
                    and l.product_id == old_line.product_id
                )
            )[:1]
            if new_parent:
                parent_map[old_line.id] = new_parent

        # Remap children
        for new_comp in new_lines.filtered('is_set_component'):
            old_parent_id = new_comp.set_parent_line_id.id
            if old_parent_id in parent_map:
                new_comp.with_context(
                    rental_set_copying=True,
                ).write({
                    'set_parent_line_id': parent_map[old_parent_id].id,
                })

        return new_order

    def _get_order_lines_to_report(self):
        """Exclude hidden Rental Set component lines from customer-facing
        documents (quotation PDF, sales order PDF, portal).

        Only lines where visible_to_customer=True (or non-component lines)
        are shown.  The parent set line carries the customer-facing
        description and price.
        """
        lines = super()._get_order_lines_to_report()
        return lines.filtered(
            lambda l: not l.is_set_component or l.visible_to_customer
        )

    def _get_invoiceable_lines(self, final=False):
        """Exclude hidden Rental Set components from invoice creation.

        Components with visible_to_customer=False should never appear on
        customer invoices.  The parent set line is the only invoiceable line.
        """
        lines = super()._get_invoiceable_lines(final=final)
        return lines.filtered(
            lambda l: not l.is_set_component or l.visible_to_customer
        )
