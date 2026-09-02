from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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

    @api.constrains('lost_broken_fee_product_id')
    def _check_lost_broken_fee_is_service(self):
        """A fee is an invoice line, never a delivery — so the fee product
        must be a service (a storable/rental product would spawn a delivery
        and re-reserve the lost item)."""
        for company in self:
            product = company.lost_broken_fee_product_id
            if product and product.type != 'service':
                raise ValidationError(_(
                    'The Lost/Broken Fee product (%(product)s) must be a '
                    'service product — a fee must not create a delivery.',
                    product=product.display_name,
                ))
