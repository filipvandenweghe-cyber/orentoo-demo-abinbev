from odoo import api, fields, models

# Business requirements: PC09
# See __init__.py for full index.


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # ------------------------------------------------------------------
    # Delegated fields — proxy to the first variant.
    # Same pattern as standard barcode / default_code.
    # Editable on the template form when product_variant_count <= 1.
    # Source of truth remains product.product.
    # ------------------------------------------------------------------

    use_in_multi_channel_rental_flow = fields.Boolean(
        string="Use in Multi-Channel Rental Flow",
        related='product_variant_ids.use_in_multi_channel_rental_flow',
        readonly=False,
    )

    multi_channel_item_role = fields.Selection(
        related='product_variant_ids.multi_channel_item_role',
        readonly=False,
    )

    available_in_multi_channel_website = fields.Boolean(
        related='product_variant_ids.available_in_multi_channel_website',
        readonly=False,
    )

    available_in_multi_channel_kiosk = fields.Boolean(
        related='product_variant_ids.available_in_multi_channel_kiosk',
        readonly=False,
    )

    requires_timeslot = fields.Boolean(
        related='product_variant_ids.requires_timeslot',
        readonly=False,
    )

    requires_duration = fields.Boolean(
        related='product_variant_ids.requires_duration',
        readonly=False,
    )

    allow_quantity_selection = fields.Boolean(
        related='product_variant_ids.allow_quantity_selection',
        readonly=False,
    )

    use_product_image_in_flow = fields.Boolean(
        related='product_variant_ids.use_product_image_in_flow',
        readonly=False,
    )

    # ------------------------------------------------------------------
    # Computed summary fields
    # ------------------------------------------------------------------

    mcrf_variant_count = fields.Integer(
        string="Variants in Flow",
        compute='_compute_mcrf_variant_count',
        help="Number of product variants enabled in the Multi-Channel Rental Flow.",
    )

    mcrf_any_variant_enabled = fields.Boolean(
        string="In Multi-Channel Flow",
        compute='_compute_mcrf_any_variant_enabled',
        store=True,
        help="True when at least one variant is enabled in the Multi-Channel Rental Flow.",
    )

    @api.depends('product_variant_ids.use_in_multi_channel_rental_flow')
    def _compute_mcrf_variant_count(self):
        for template in self:
            template.mcrf_variant_count = len(
                template.product_variant_ids.filtered(
                    'use_in_multi_channel_rental_flow'
                )
            )

    @api.depends('product_variant_ids.use_in_multi_channel_rental_flow')
    def _compute_mcrf_any_variant_enabled(self):
        for template in self:
            template.mcrf_any_variant_enabled = any(
                template.product_variant_ids.mapped(
                    'use_in_multi_channel_rental_flow'
                )
            )
