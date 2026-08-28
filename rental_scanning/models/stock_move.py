from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    # The SOURCE package(s) a move was picked from (via scanning).  Distinct
    # from the standard 'Packages' column, which shows the RESULT/shipping
    # package (empty here by design under Option iii — the pack dissolves at
    # delivery and goods ship as products).
    rental_scanning_src_package_ids = fields.Many2many(
        'stock.package',
        string='From Package',
        compute='_compute_rental_scanning_src_package_ids',
    )

    @api.depends('move_line_ids.package_id')
    def _compute_rental_scanning_src_package_ids(self):
        for move in self:
            move.rental_scanning_src_package_ids = \
                move.move_line_ids.package_id
