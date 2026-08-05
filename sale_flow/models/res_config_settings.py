from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sale_flow_skip_invoice_logistics = fields.Boolean(
        string='Do not add on Invoice if added by Logistics',
        related='company_id.sale_flow_skip_invoice_logistics',
        readonly=False,
        help=(
            'When enabled, products added by logistics during delivery '
            'will NOT be automatically added to the invoice.'
        ),
    )

    lost_broken_fee_product_id = fields.Many2one(
        'product.product',
        string='Default Lost/Broken Fee Product',
        related='company_id.lost_broken_fee_product_id',
        readonly=False,
        help=(
            'Product used for lost/broken charge invoice lines. '
            'Determines the tax and accounting behavior.'
        ),
    )
