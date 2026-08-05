from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    auto_reconcile_delivered_qty = fields.Boolean(
        string='Auto-reconcile Ordered Quantity',
        default=False,
        help=(
            'When enabled, the ordered quantity on the sale order line is '
            'automatically adjusted to match the actually delivered quantity '
            'once all logistics are complete (all pickings done/cancelled). '
            'This prevents the "upselling" status and ensures the invoice '
            'reflects reality. When disabled (default), standard Odoo '
            'behavior applies and the user must reconcile manually.'
        ),
    )

    sales_price_broken_lost = fields.Float(
        string='Sales Price Broken / Lost',
        digits='Product Price',
        help=(
            'Default price charged when a rental product is lost or broken. '
            'If empty or zero, lost/broken invoice lines are still created '
            'with price 0.'
        ),
    )
