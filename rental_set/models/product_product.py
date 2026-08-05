from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # The set component listing is no longer appended to the sale
    # description.  Standard Odoo logic applies: the quotation line
    # uses the description_sale defined on the product's Sales tab.
