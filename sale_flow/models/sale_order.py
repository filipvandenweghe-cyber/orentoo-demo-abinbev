"""Sale order extensions for sale_flow.

Implements: R01, R02, R11, R12, R17.
See sale_flow_line.py module docstring for the full requirements index.
"""

from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    flow_line_ids = fields.One2many(
        'sale.flow.line',
        'sale_order_id',
        string='Flow Lines',
    )
    flow_line_count = fields.Integer(
        string='Flow Line Count',
        compute='_compute_flow_line_count',
    )

    @api.depends('flow_line_ids')
    def _compute_flow_line_count(self):
        for order in self:
            order.flow_line_count = len(order.flow_line_ids)

    # ── Rental status integration ──────────────────────────────────────

    @api.depends(
        'order_line.is_rental',
        'order_line.product_uom_qty',
        'order_line.qty_delivered',
        'order_line.qty_returned',
    )
    def _compute_has_action_lines(self):
        """Override to consider stock move reality, not just qty comparison.

        Pickable fix:
          Standard Odoo decides has_pickable_lines by comparing
          qty_delivered < product_uom_qty.  This is wrong when all outgoing
          pickings are fully processed (done/cancelled) — there is nothing
          left to pick up even if qty_delivered < ordered qty.

          Business rule: if all outgoing stock moves for a rental order are
          in a terminal state (done or cancel), the pickup is complete.
          You cannot pick up something that has already been picked up.

        Returnable fix:
          Standard Odoo only checks sale order lines.  If a rental product
          was added during delivery (e.g. an extra projector), it has no
          sale order line and the standard check would miss it.

          Business rule: if any return picking has pending moves (not
          done/cancel), there are items to return — regardless of whether
          they appear on a sale order line.
        """
        super()._compute_has_action_lines()
        for order in self:
            if not order.is_rental_order or order.state != 'sale':
                continue

            # ── Pickable: all outgoing moves done → nothing left to pick up
            if order.has_pickable_lines:
                outgoing_pickings = order.picking_ids.filtered(
                    lambda p: not p.return_id
                )
                if outgoing_pickings:
                    has_pending_outgoing = any(
                        move.state not in ('done', 'cancel')
                        for pick in outgoing_pickings
                        for move in pick.move_ids
                    )
                    if not has_pending_outgoing:
                        order.has_pickable_lines = False

            # ── Returnable: also check return pickings for pending moves
            #    that may not be linked to a sale order line (e.g. products
            #    added during delivery).
            #    Only flag as returnable if the pickup is actually complete
            #    (has_pickable_lines is False).  Before pickup, the return
            #    picking may already exist (pre-created by reconciliation)
            #    but it's not yet relevant — nothing was delivered.
            if not order.has_returnable_lines and not order.has_pickable_lines:
                return_pickings = order.picking_ids.filtered(
                    lambda p: p.return_id and p.state not in ('done', 'cancel')
                )
                if return_pickings:
                    has_pending_returns = any(
                        move.state not in ('done', 'cancel')
                        and move.product_uom_qty > 0
                        for pick in return_pickings
                        for move in pick.move_ids
                    )
                    if has_pending_returns:
                        order.has_returnable_lines = True

    # ── Auto-reconcile ordered qty ─────────────────────────────────────

    def _auto_reconcile_delivered_qty(self):
        """Auto-adjust ordered qty to match delivered qty for flagged products.

        Business rule (R19): for products with auto_reconcile_delivered_qty
        enabled, the SOL product_uom_qty is adjusted to match qty_delivered
        once all logistics are complete.  This prevents the 'upselling'
        status and ensures the invoice reflects actual delivery.

        Products without the flag keep standard Odoo behavior (user must
        reconcile manually via the upselling opportunity).

        Triggered after all pickings are done — i.e. when has_pickable_lines
        and has_returnable_lines are both False.
        """
        for order in self:
            if order.state != 'sale':
                continue
            # Only run when all logistics are complete
            if order.has_pickable_lines or order.has_returnable_lines:
                continue

            for line in order.order_line:
                if line.display_type:
                    continue
                if not line.product_id.auto_reconcile_delivered_qty:
                    continue
                if line.qty_invoiced > line.qty_delivered:
                    # Already invoiced more than delivered — don't reduce
                    continue

                prec = self.env['decimal.precision'].precision_get(
                    'Product Unit of Measure'
                )
                from odoo.tools import float_compare
                if float_compare(
                    line.product_uom_qty, line.qty_delivered,
                    precision_digits=prec,
                ) != 0:
                    line.with_context(
                        skip_sale_flow_sync=True,
                        skip_procurement=True,
                    ).write({
                        'product_uom_qty': line.qty_delivered,
                    })
                    # Update flow line current_qty to match
                    for fl in line.flow_line_ids.filtered(
                        lambda f: f.state not in ('cancelled', 'invoiced')
                    ):
                        fl.with_context(skip_sale_flow_sync=True).write({
                            'current_qty': line.qty_delivered,
                            'was_changed_after_confirmation': True,
                            'change_origin': 'system',
                            'change_note': _(
                                'Auto-reconciled: ordered qty adjusted '
                                'from %(old)s to %(new)s to match delivered',
                                old=line.product_uom_qty,
                                new=line.qty_delivered,
                            ),
                        })

    # ── Confirmation hook ────────────────────────────────────────────────

    def action_confirm(self):
        """Create/update sale.flow.line records when the order is confirmed.

        Business rule: the confirmed sale order is the agreed commercial
        baseline.  At confirmation we snapshot qty, price, discount,
        subtotal and description for each line.
        """
        res = super().action_confirm()
        for order in self:
            if order.state == 'sale':
                self.env['sale.flow.service']._on_order_confirmed(order)
        return res

    def action_cancel(self):
        """Mark flow lines as cancelled when the order is cancelled."""
        res = super().action_cancel()
        for order in self:
            order.flow_line_ids.filtered(
                lambda fl: fl.state != 'invoiced'
            ).write({'state': 'cancelled'})
        return res

    # ── Manual initialization for existing orders ────────────────────────

    def action_initialize_flow_lines(self):
        """Admin action: create flow lines for an existing confirmed order.

        Existing orders created before sale_flow was installed do not
        have flow lines.  This action lets the admin initialize them
        manually.  New orders use sale flow automatically.
        """
        for order in self:
            if order.state != 'sale':
                continue
            self.env['sale.flow.service']._on_order_confirmed(order)
        return True

    # ── Smart button ─────────────────────────────────────────────────────

    def action_view_flow_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Flow Lines'),
            'res_model': 'sale.flow.line',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }
