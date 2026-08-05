from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    sale_flow_skip_invoice_logistics = fields.Boolean(
        string='Do not add on Invoice if added by Logistics',
        default=False,
        help=(
            'When enabled, products added by logistics during delivery '
            'will NOT be automatically added to the invoice. '
            'When disabled (default), all delivered sale articles are '
            'added to the invoice regardless of who added them.'
        ),
    )

    lost_broken_fee_product_id = fields.Many2one(
        'product.product',
        string='Default Lost/Broken Fee Product',
        help=(
            'Product used for lost/broken charge invoice lines. '
            'Determines the tax and accounting behavior. '
            'The invoice line description will mention the actual '
            'lost/broken product (e.g. "Lost/Broken Fee -- Speaker A").'
        ),
    )
