from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleFlowLostBrokenWizard(models.TransientModel):
    """Wizard for handling missing or damaged rental items.

    Opened when a return picking is validated and some delivered rental
    quantities are still unaccounted for.  Works in both scenarios:

      * No backorder: items are definitively missing.
      * With backorder: items are on a backorder, but the user may
        already know some are lost or broken.

    The wizard defaults lost and broken to 0 — the user decides.
    If the user fills in lost/broken quantities:
      * Charge lines are created for those items.
      * The backorder demand is reduced by the lost/broken qty.
      * Remaining (missing - lost - broken) stays on the backorder.

    Constraint: missing >= lost + broken (you cannot have more broken
    or lost items than those that are missing).
    """

    _name = 'sale.flow.lost.broken.wizard'
    _description = 'Lost/Broken Items Wizard'

    picking_id = fields.Many2one(
        'stock.picking',
        string='Return Picking',
        readonly=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        readonly=True,
    )
    line_ids = fields.One2many(
        'sale.flow.lost.broken.wizard.line',
        'wizard_id',
        string='Lines',
    )

    def action_confirm(self):
        """Confirm lost/broken quantities and create charge lines.

        If any lost/broken qty is specified:
          1. Create charge lines via the lost/broken service.
          2. Reduce backorder demand for the processed quantities.
        If all lost/broken are 0, just close (wait for backorder).
        """
        self.ensure_one()

        # Validate constraints
        prec = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        for wiz_line in self.line_ids:
            total = (wiz_line.lost_qty or 0) + (wiz_line.broken_qty or 0)
            if float_compare(total, wiz_line.missing_qty, precision_digits=prec) > 0:
                raise UserError(_(
                    'Lost + Broken (%(total)s) cannot exceed missing quantity '
                    '(%(missing)s) for product %(product)s.',
                    total=total,
                    missing=wiz_line.missing_qty,
                    product=wiz_line.product_id.display_name,
                ))

        # Check if user actually marked anything as lost/broken
        has_lost_broken = any(
            float_compare(
                (wl.lost_qty or 0) + (wl.broken_qty or 0), 0,
                precision_digits=prec,
            ) > 0
            for wl in self.line_ids
        )

        if has_lost_broken:
            # Process lost/broken charges
            self.env['sale.flow.lost.broken.service']._process_lost_broken(self)

            # Reduce backorder demand for processed quantities
            self._reduce_backorder_demand()

        return {'type': 'ir.actions.act_window_close'}

    def _reduce_backorder_demand(self):
        """Reduce backorder moves for items classified as lost or broken.

        Business rule: if the user marks items as lost/broken while a
        backorder exists, those items should no longer be expected on the
        backorder.  The backorder demand is reduced accordingly.  If the
        entire backorder demand is consumed, the move is cancelled.
        """
        if not self.picking_id or not self.sale_order_id:
            return

        prec = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        # Find backorder pickings (return pickings not yet done for this order)
        backorder_pickings = self.sale_order_id.picking_ids.filtered(
            lambda p: (
                p.return_id
                and p.state not in ('done', 'cancel')
                and p.id != self.picking_id.id
            )
        )
        if not backorder_pickings:
            return

        for wiz_line in self.line_ids:
            processed = (wiz_line.lost_qty or 0) + (wiz_line.broken_qty or 0)
            if float_compare(processed, 0, precision_digits=prec) <= 0:
                continue

            remaining_to_reduce = processed

            for picking in backorder_pickings:
                if float_compare(remaining_to_reduce, 0, precision_digits=prec) <= 0:
                    break

                for move in picking.move_ids.filtered(
                    lambda m: (
                        m.product_id == wiz_line.product_id
                        and m.state not in ('done', 'cancel')
                    )
                ):
                    current_demand = move.product_uom_qty
                    reduce_by = min(remaining_to_reduce, current_demand)

                    new_demand = current_demand - reduce_by
                    if float_compare(new_demand, 0, precision_digits=prec) <= 0:
                        # Cancel the entire move
                        move.with_context(skip_sale_flow_sync=True)._action_cancel()
                    else:
                        move.with_context(skip_sale_flow_sync=True).write({
                            'product_uom_qty': new_demand,
                        })

                    remaining_to_reduce -= reduce_by


class SaleFlowLostBrokenWizardLine(models.TransientModel):
    _name = 'sale.flow.lost.broken.wizard.line'
    _description = 'Lost/Broken Wizard Line'

    wizard_id = fields.Many2one(
        'sale.flow.lost.broken.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    flow_line_id = fields.Many2one(
        'sale.flow.line',
        string='Flow Line',
        required=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        readonly=True,
    )
    delivered_qty = fields.Float(
        string='Delivered Qty',
        digits='Product Unit of Measure',
        readonly=True,
    )
    returned_qty = fields.Float(
        string='Returned Qty',
        digits='Product Unit of Measure',
        readonly=True,
    )
    missing_qty = fields.Float(
        string='Missing Qty',
        digits='Product Unit of Measure',
        readonly=True,
    )
    lost_qty = fields.Float(
        string='Lost Qty',
        digits='Product Unit of Measure',
        help='Items not returned at all.',
    )
    broken_qty = fields.Float(
        string='Broken Qty',
        digits='Product Unit of Measure',
        help='Items returned damaged.',
    )
    broken_lost_unit_price = fields.Float(
        string='Broken/Lost Unit Price',
        digits='Product Price',
        help='Price charged per unit for lost or broken items.',
    )

    @api.onchange('lost_qty', 'broken_qty')
    def _onchange_quantities(self):
        """Warn if lost + broken exceeds missing."""
        for line in self:
            total = (line.lost_qty or 0) + (line.broken_qty or 0)
            if total > line.missing_qty:
                return {
                    'warning': {
                        'title': _('Quantity Warning'),
                        'message': _(
                            'Lost + Broken (%(total)s) cannot exceed '
                            'missing quantity (%(missing)s).',
                            total=total, missing=line.missing_qty,
                        ),
                    }
                }
