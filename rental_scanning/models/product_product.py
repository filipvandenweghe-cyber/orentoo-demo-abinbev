from odoo import api, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _get_fields_stock_barcode(self):
        # Expose is_rental_set to the Barcode client so a scanned set barcode
        # can be routed through the rental_scanning reconciliation (PPB-12).
        return super()._get_fields_stock_barcode() + ['is_rental_set']
