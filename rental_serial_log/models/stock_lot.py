from odoo import fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    rental_log_ids = fields.One2many(
        'rental.serial.log', 'lot_id', string='Rental History')
