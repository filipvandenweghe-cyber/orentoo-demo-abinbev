# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Stored so the Rental Purchase order can expose its return pickings via a
    # One2many / smart button (§17, §24).
    rental_purchase_return_order_id = fields.Many2one(
        'purchase.order',
        string="Rental Purchase (Return)",
        compute='_compute_rental_purchase_return_order_id',
        store=True,
        index='btree_not_null',
    )

    @api.depends('move_ids.rental_purchase_order_id')
    def _compute_rental_purchase_return_order_id(self):
        for picking in self:
            orders = picking.move_ids.rental_purchase_order_id
            picking.rental_purchase_return_order_id = orders[:1]
