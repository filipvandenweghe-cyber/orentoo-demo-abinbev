"""Stock move extensions for sale_flow.

Implements: R08, R16.
See sale_flow_line.py module docstring for the full requirements index.
"""

from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    sale_flow_line_id = fields.Many2one(
        'sale.flow.line',
        string='Sale Flow Line',
        index=True,
        ondelete='set null',
        help='Link to the sale.flow.line this move contributes to.',
    )

    def _action_done(self, cancel_backorder=False):
        """After moves are done, update linked sale.flow.line quantities.

        Business rule: let standard Odoo stock behavior run first,
        then update the flow line operational quantities.
        """
        res = super()._action_done(cancel_backorder=cancel_backorder)

        if self.env.context.get('skip_sale_flow_sync'):
            return res

        self.env['sale.flow.sync.service']._sync_moves_to_flow(self)
        return res
