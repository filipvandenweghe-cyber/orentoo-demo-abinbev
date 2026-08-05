"""Sale order line extensions for sale_flow.

Implements: R03, R04, R05, R16.
See sale_flow_line.py module docstring for the full requirements index.
"""

from odoo import api, fields, models
from odoo.tools import float_compare


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    flow_line_ids = fields.One2many(
        'sale.flow.line',
        'sale_line_id',
        string='Flow Lines',
    )

    def write(self, vals):
        """After standard write, reconcile changes into sale.flow.line.

        Business rule: let Odoo perform its normal synchronization first,
        then reconcile the result into sale.flow.line.  The confirmed
        baseline is never overwritten by post-confirmation changes.
        """
        if self.env.context.get('skip_sale_flow_sync'):
            return super().write(vals)

        # Capture pre-write state for reconciliation
        pre_state = {}
        flow_relevant_fields = {'product_uom_qty', 'price_unit', 'discount'}
        if flow_relevant_fields & set(vals.keys()):
            for line in self:
                pre_state[line.id] = {
                    'product_uom_qty': line.product_uom_qty,
                    'price_unit': line.price_unit,
                    'discount': line.discount,
                }

        res = super().write(vals)

        # Reconcile into flow lines after standard write completes
        if pre_state:
            for line in self:
                if line.id not in pre_state:
                    continue
                flow_lines = line.flow_line_ids.filtered(
                    lambda fl: fl.state not in ('cancelled', 'invoiced')
                )
                if not flow_lines:
                    continue
                self.env['sale.flow.service']._reconcile_line_change(
                    line, pre_state[line.id], flow_lines,
                )
        return res

    def unlink(self):
        """Protect flow lines with logistic history from hard deletion.

        Business rule: if delivered_qty > 0, do not allow deletion.
        The user must handle this through return, credit, lost or broken flow.
        If no logistic history exists, allow normal deletion.
        """
        if self.env.context.get('skip_sale_flow_sync'):
            return super().unlink()

        for line in self:
            flow_lines = line.flow_line_ids
            if not flow_lines:
                continue
            for fl in flow_lines:
                if float_compare(fl.delivered_qty, 0, precision_digits=2) > 0:
                    # Cannot delete -- treat as qty decrease to zero
                    self.env['sale.flow.service']._handle_line_deletion(line, fl)
                    return True  # prevent actual deletion

        return super().unlink()
