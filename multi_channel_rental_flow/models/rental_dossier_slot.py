from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# Business requirements: DS01–DS06
# See __init__.py for full index.

SLOT_STATES = [
    ('draft', "Draft"),
    ('order_created', "Order Created"),
    ('confirmed', "Confirmed"),
    ('cancelled', "Cancelled"),
]


class RentalDossierSlot(models.Model):
    """One slot = one rental timeslot (start + end datetime).  [DS01]"""

    _name = 'rental.dossier.slot'
    _description = 'Rental Dossier Slot'
    _order = 'sequence, start_datetime, id'

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    dossier_id = fields.Many2one(
        'rental.dossier',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(
        string="Slot",
        compute='_compute_name',
        store=True,
    )
    sequence = fields.Integer(default=10)
    state = fields.Selection(
        selection=SLOT_STATES,
        default='draft',
        required=True,
    )

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    start_datetime = fields.Datetime(
        string="Start",
        required=True,
    )
    end_datetime = fields.Datetime(
        string="End",
        required=True,
    )

    # ------------------------------------------------------------------
    # Warehouse — defaults from dossier / profile
    # ------------------------------------------------------------------

    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string="Warehouse",
    )
    company_id = fields.Many2one(
        related='dossier_id.company_id',
        store=True,
    )

    # ------------------------------------------------------------------
    # Items in this slot
    # ------------------------------------------------------------------

    item_ids = fields.One2many(
        'rental.dossier.item',
        'slot_id',
        string="Items",
    )
    item_count = fields.Integer(
        compute='_compute_item_count',
    )

    # ------------------------------------------------------------------
    # Generated sale order (one per slot)
    # ------------------------------------------------------------------

    sale_order_id = fields.Many2one(
        'sale.order',
        string="Sale Order",
        copy=False,
    )

    # ------------------------------------------------------------------
    # Computed
    # ------------------------------------------------------------------

    @api.depends('start_datetime', 'end_datetime', 'sequence')
    def _compute_name(self):
        for slot in self:
            if slot.start_datetime and slot.end_datetime:
                start = fields.Datetime.context_timestamp(
                    slot, slot.start_datetime,
                )
                end = fields.Datetime.context_timestamp(
                    slot, slot.end_datetime,
                )
                if start.date() == end.date():
                    slot.name = _(
                        "%(date)s %(start)s – %(end)s",
                        date=start.strftime('%d/%m/%Y'),
                        start=start.strftime('%H:%M'),
                        end=end.strftime('%H:%M'),
                    )
                else:
                    slot.name = _(
                        "%(start)s – %(end)s",
                        start=start.strftime('%d/%m/%Y %H:%M'),
                        end=end.strftime('%d/%m/%Y %H:%M'),
                    )
            else:
                slot.name = _("Slot %s", slot.sequence)

    @api.depends('item_ids')
    def _compute_item_count(self):
        for slot in self:
            slot.item_count = len(slot.item_ids)

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------

    @api.onchange('dossier_id')
    def _onchange_dossier_id(self):
        if self.dossier_id and not self.warehouse_id:
            self.warehouse_id = self.dossier_id.warehouse_id

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @api.constrains('start_datetime', 'end_datetime')
    def _check_dates(self):
        for slot in self:
            if slot.start_datetime and slot.end_datetime:
                if slot.start_datetime >= slot.end_datetime:
                    raise ValidationError(
                        _("Slot start must be before end (%(slot)s).",
                          slot=slot.display_name)
                    )
