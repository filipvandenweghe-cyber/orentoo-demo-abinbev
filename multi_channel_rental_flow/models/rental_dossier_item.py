from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# Business requirements: DI01–DI12
# See __init__.py for full index.

ITEM_ROLES = [
    ('rental', "Rental"),
    ('event_ticket', "Event Ticket"),
    ('addon', "Add-on"),
    ('service', "Service"),
    ('flex_option', "Flex Option"),
]

ITEM_STATES = [
    ('draft', "Draft"),
    ('priced', "Priced"),
    ('generated', "Generated"),
    ('confirmed', "Confirmed"),
    ('cancelled', "Cancelled"),
    ('exception', "Exception"),
]

AVAILABILITY_STATES = [
    ('unknown', "Unknown"),
    ('available', "Available"),
    ('unavailable', "Unavailable"),
    ('outside_opening_hours', "Outside Opening Hours"),
]


class RentalDossierItem(models.Model):
    """One product line in the dossier.  [DI01]"""

    _name = 'rental.dossier.item'
    _description = 'Rental Dossier Item'
    _order = 'slot_id, sequence, id'

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    dossier_id = fields.Many2one(
        'rental.dossier',
        required=True,
        ondelete='cascade',
        index=True,
    )
    slot_id = fields.Many2one(
        'rental.dossier.slot',
        string="Slot",
        ondelete='cascade',
        help="Timeslot this item belongs to. Empty for non-slot items.",
    )
    sequence = fields.Integer(default=10)

    state = fields.Selection(
        selection=ITEM_STATES,
        default='draft',
        required=True,
    )
    availability_state = fields.Selection(
        selection=AVAILABILITY_STATES,
        default='unknown',
    )

    # ------------------------------------------------------------------
    # Product / role
    # ------------------------------------------------------------------

    item_role = fields.Selection(
        selection=ITEM_ROLES,
        string="Role",
        required=True,
        default='rental',
    )
    product_id = fields.Many2one(
        'product.product',
        string="Product",
        required=True,
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string="Unit of Measure",
        compute='_compute_product_uom_id',
        store=True,
        precompute=True,
        readonly=False,
    )
    quantity = fields.Float(
        default=1.0,
    )

    # ------------------------------------------------------------------
    # Event fields  [EV01–EV08]
    # Many2one to event models — works safely even if event module
    # is uninstalled (fields just become invisible/unused).
    # ------------------------------------------------------------------

    event_id = fields.Many2one(
        'event.event',
        string="Event",
        help="Event for event_ticket items.",
    )
    event_ticket_id = fields.Many2one(
        'event.event.ticket',
        string="Event Ticket",
        help="Ticket type for event_ticket items.",
    )
    event_slot_id = fields.Many2one(
        'event.slot',
        string="Event Slot",
        help="Event time slot (for multi-slot events).",
    )

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    price_unit = fields.Float(
        string="Unit Price",
        digits='Product Price',
    )
    price_subtotal = fields.Float(
        string="Subtotal",
        compute='_compute_price_subtotal',
        store=True,
        digits='Product Price',
    )

    # Coefficient & dynamic pricing preview
    coefficient = fields.Float(
        string="Coefficient",
        default=1.0,
        help="Duration coefficient from rental_coefficient_dynamic_pricing.",
    )
    dynamic_factor_percentage = fields.Float(
        string="Dynamic Factor (%)",
        default=100.0,
        help="Dynamic pricing factor percentage.",
    )
    dynamic_multiplier = fields.Float(
        string="Dynamic Multiplier",
        compute='_compute_dynamic_multiplier',
        store=True,
    )
    color_code = fields.Char(
        string="Color Code",
        help="Hex color for the dynamic pricing factor display.",
    )

    # ------------------------------------------------------------------
    # Currency (from dossier)
    # ------------------------------------------------------------------

    currency_id = fields.Many2one(
        related='dossier_id.currency_id',
    )
    company_id = fields.Many2one(
        related='dossier_id.company_id',
        store=True,
    )

    # ------------------------------------------------------------------
    # Generated records — linked after order generation
    # ------------------------------------------------------------------

    sale_order_line_id = fields.Many2one(
        'sale.order.line',
        string="Sale Order Line",
        copy=False,
    )

    registration_ids = fields.One2many(
        'event.registration',
        'mcrf_dossier_item_id',
        string="Registrations",
        copy=False,
    )

    # ------------------------------------------------------------------
    # Computed
    # ------------------------------------------------------------------

    @api.depends('product_id')
    def _compute_product_uom_id(self):
        for item in self:
            if item.product_id:
                item.product_uom_id = item.product_id.uom_id
            elif not item.product_uom_id:
                item.product_uom_id = False

    @api.depends('price_unit', 'quantity')
    def _compute_price_subtotal(self):
        for item in self:
            item.price_subtotal = item.price_unit * item.quantity

    @api.depends('dynamic_factor_percentage')
    def _compute_dynamic_multiplier(self):
        for item in self:
            item.dynamic_multiplier = (
                item.dynamic_factor_percentage / 100.0
                if item.dynamic_factor_percentage
                else 1.0
            )

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains('quantity')
    def _check_quantity(self):
        for item in self:
            if item.quantity <= 0:
                raise ValidationError(
                    _("Quantity must be positive for '%(product)s'.",
                      product=item.product_id.display_name)
                )

    # ------------------------------------------------------------------
    # Onchange helpers
    # ------------------------------------------------------------------

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Set item role and defaults from product configuration."""
        if self.product_id:
            pp = self.product_id
            if pp.use_in_multi_channel_rental_flow:
                self.item_role = pp.multi_channel_item_role
            if not self.product_uom_id:
                self.product_uom_id = pp.uom_id

    @api.onchange('product_id', 'quantity', 'coefficient',
                   'dynamic_factor_percentage')
    def _onchange_pricing(self):
        """Recalculate preview price. Full pricing integration later."""
        if self.product_id and self.product_id.lst_price:
            base = self.product_id.lst_price
            coeff = self.coefficient or 1.0
            mult = (self.dynamic_factor_percentage or 100.0) / 100.0
            self.price_unit = base * coeff * mult
