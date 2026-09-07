# -*- coding: utf-8 -*-
from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    # Explicit relational traceability (§17): every move that belongs to the
    # automatically generated supplier-return chain points back to its
    # Rental Purchase order.
    rental_purchase_order_id = fields.Many2one(
        'purchase.order',
        string="Rental Purchase (Return)",
        index='btree_not_null',
        copy=False,
    )

    def _action_done(self, cancel_backorder=False):
        """After receipts (or returns) complete, re-size the supplier-return
        obligation to what was ACTUALLY received - the mirror, on the receipt
        leg, of the delivery-side return-demand reconciliation.  Isolated to
        Rental Purchase moves, so ordinary purchases and the sales/rental flow
        are never touched.
        """
        res = super()._action_done(cancel_backorder=cancel_backorder)
        orders = self.filtered(
            lambda m: m.picking_code == 'incoming' and m.purchase_line_id
            and m.purchase_line_id.order_id.is_rental_purchase
        ).purchase_line_id.order_id
        orders |= self.filtered('rental_purchase_order_id').rental_purchase_order_id
        if orders:
            orders._rental_purchase_reconcile_returns()
        return res
