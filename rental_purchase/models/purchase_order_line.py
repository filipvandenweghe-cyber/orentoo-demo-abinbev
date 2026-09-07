# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # Convenience related field (used by the account determination and views).
    is_rental_purchase = fields.Boolean(
        related='order_id.is_rental_purchase',
        store=True,
    )
