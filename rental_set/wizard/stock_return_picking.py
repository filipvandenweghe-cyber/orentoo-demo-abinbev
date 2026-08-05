from odoo import models


class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    def _prepare_stock_return_picking_line_vals_from_move(self, stock_move):
        """Skip set parent header moves from the return wizard.

        Set parent header moves are display-only entries on outbound
        pickings (demand=set qty, picked=True).  They should never
        appear on return pickings because:
          * The set parent product carries no stock of its own.
          * Only the actual components need to be returned.
          * Return reconciliation (_reconcile_return_pickings) handles
            component-level return demands correctly.

        We return an empty dict with quantity=0 so the line is effectively
        skipped (the wizard filters out zero-qty lines on create_returns).
        """
        sol = stock_move.sale_line_id
        if sol and sol.is_set and not sol.is_set_component:
            vals = super()._prepare_stock_return_picking_line_vals_from_move(stock_move)
            vals['quantity'] = 0
            return vals
        return super()._prepare_stock_return_picking_line_vals_from_move(stock_move)
