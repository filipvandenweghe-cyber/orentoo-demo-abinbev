from odoo import api, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.depends(
        'is_rental_order', 'state',
        'order_line.is_rental', 'order_line.product_uom_qty',
        'order_line.qty_delivered', 'order_line.qty_returned',
        'order_line.is_set',
        'picking_ids.state', 'picking_ids.return_id',
    )
    def _compute_has_action_lines(self):
        """Refine the rental pickup/return status.

        1) Exclude rental-set HEADER lines: a set parent (and nested set
           headers) carry no stock moves, so their qty_delivered stays 0 and
           would make the order look permanently 'to pick up'.  The real
           status comes from the set's component lines.

        2) The Pickup button is driven by OPEN OUTGOING warehouse operations,
           not by delivered-vs-ordered qty.  Once every outgoing picking is
           done/cancelled (e.g. a no-backorder short delivery) there is
           nothing left to pick up — WITHOUT changing the ordered quantity
           (we must keep what the client asked for, and the warehouse may
           still adjust set contents).
        """
        super()._compute_has_action_lines()
        for order in self:
            if order.state != 'sale' or not order.is_rental_order:
                continue

            # (1) Ignore set-header lines in the per-line status.
            lines = order.order_line.filtered(
                lambda l: l.is_rental and l.product_type != 'combo'
                and not l.is_set
            )
            order.has_pickable_lines = any(
                sol.qty_delivered < sol.product_uom_qty for sol in lines)
            order.has_returnable_lines = any(
                sol.qty_returned < sol.qty_delivered for sol in lines)

            # (2) No open outgoing operation => nothing left to pick up.
            outgoing = order.picking_ids.filtered(lambda p: not p.return_id)
            if outgoing and not outgoing.filtered(
                    lambda p: p.state not in ('done', 'cancel')):
                order.has_pickable_lines = False

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
