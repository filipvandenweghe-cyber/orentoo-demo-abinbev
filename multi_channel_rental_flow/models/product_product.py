from odoo import api, fields, models

# Business requirements: PC01–PC09
# See __init__.py for full index.


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # ------------------------------------------------------------------
    # Multi-Channel Rental Flow — product-level configuration  [PC01]
    # ------------------------------------------------------------------

    use_in_multi_channel_rental_flow = fields.Boolean(  # PC02
        string="Use in Multi-Channel Rental Flow",
        default=False,
        help=(
            "Enable this product in the Multi-Channel Rental Flow. "
            "When enabled, configure the item role and channel availability below."
        ),
    )

    multi_channel_item_role = fields.Selection(  # PC03
        selection=[
            ('rental', "Rental"),
            ('event_ticket', "Event Ticket"),
            ('addon', "Add-on"),
            ('service', "Service"),
            ('flex_option', "Flex Option"),
        ],
        string="Multi-Channel Item Role",
        default='rental',
        help=(
            "Determines how this product behaves in the flow:\n"
            "- Rental: requires timeslot and duration selection.\n"
            "- Event Ticket: requires event and ticket selection.\n"
            "- Add-on: optional extra (e.g. lunch package).\n"
            "- Service: standalone service product.\n"
            "- Flex Option: reserved for future use."
        ),
    )

    available_in_multi_channel_website = fields.Boolean(  # PC04
        string="Available in Multi-Channel Website Flow",
        default=False,
        help="Make this product available in the website rental flow.",
    )

    available_in_multi_channel_kiosk = fields.Boolean(  # PC04
        string="Available in Multi-Channel Kiosk Flow",
        default=False,
        help="Make this product available in kiosk terminals.",
    )

    requires_timeslot = fields.Boolean(  # PC05
        string="Requires Timeslot",
        default=False,
        help=(
            "When enabled, the customer must select a start time "
            "for this product in the flow."
        ),
    )

    requires_duration = fields.Boolean(  # PC05
        string="Requires Duration",
        default=False,
        help=(
            "When enabled, the customer must select a rental duration. "
            "Duration options come from the applicable coefficient table "
            "or from the flow configuration fallback list."
        ),
    )

    allow_quantity_selection = fields.Boolean(  # PC05
        string="Allow Quantity Selection",
        default=True,
        help="Allow the customer to choose a quantity in the flow.",
    )

    use_product_image_in_flow = fields.Boolean(  # PC06
        string="Use Product Image in Flow",
        default=True,
        help="Display the product image in the website and kiosk flows.",
    )

    # ------------------------------------------------------------------
    # Defaults based on role
    # ------------------------------------------------------------------

    @api.onchange('multi_channel_item_role')
    def _onchange_multi_channel_item_role(self):  # PC07
        """Set sensible defaults when the item role changes."""
        for product in self:
            role = product.multi_channel_item_role
            if role == 'rental':
                product.requires_timeslot = True
                product.requires_duration = True
            elif role == 'event_ticket':
                product.requires_timeslot = False
                product.requires_duration = False
            elif role in ('addon', 'service'):
                product.requires_timeslot = False
                product.requires_duration = False

    @api.onchange('use_in_multi_channel_rental_flow')
    def _onchange_use_in_multi_channel_rental_flow(self):  # PC08
        """Clear channel flags when the master toggle is turned off."""
        for product in self:
            if not product.use_in_multi_channel_rental_flow:
                product.available_in_multi_channel_website = False
                product.available_in_multi_channel_kiosk = False

    # ------------------------------------------------------------------
    # Domain helpers — used by controllers / services later
    # ------------------------------------------------------------------

    @api.model
    def _mcrf_website_domain(self, website=None):
        """Return a base domain for products available in the website flow.

        Caller may extend this with category / include / exclude filters.
        """
        domain = [
            ('use_in_multi_channel_rental_flow', '=', True),
            ('available_in_multi_channel_website', '=', True),
        ]
        if website:
            domain += [
                '|',
                ('product_tmpl_id.website_id', '=', False),
                ('product_tmpl_id.website_id', '=', website.id),
            ]
        return domain

    @api.model
    def _mcrf_kiosk_domain(self):
        """Return a base domain for products available in the kiosk flow.

        Caller may extend this with kiosk-specific category / include /
        exclude filters from the flow configuration.
        """
        return [
            ('use_in_multi_channel_rental_flow', '=', True),
            ('available_in_multi_channel_kiosk', '=', True),
        ]

    @api.model
    def _mcrf_role_domain(self, role):
        """Return a domain filter for a specific item role."""
        return [('multi_channel_item_role', '=', role)]
