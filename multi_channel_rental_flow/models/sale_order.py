from odoo import api, fields, models

# Business requirements: SO01–SO07
# See __init__.py for full index.


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    mcrf_tickets_printed = fields.Boolean(
        string="Tickets Printed",
        copy=False,
        help=(
            "Checked when tickets for this order have been printed. "
            "Uncheck in backend to allow reprinting."
        ),
    )

    mcrf_dossier_id = fields.Many2one(
        'rental.dossier',
        string="Rental Dossier",
        copy=False,
        index=True,
        help="Primary dossier that generated this sale order.",
    )
    mcrf_dossier_ids = fields.Many2many(
        'rental.dossier',
        'mcrf_dossier_sale_order_rel',
        'order_id',
        'dossier_id',
        string="Dossiers",
        help="Dossiers this sale order belongs to.",
    )
    mcrf_dossier_display = fields.Char(
        string="Dossier",
        compute='_compute_mcrf_dossier_display',
        store=True,
        help="Dossier number and description for list view display.",
    )
    mcrf_dossier_slot_id = fields.Many2one(
        'rental.dossier.slot',
        string="Dossier Slot",
        copy=False,
        help="Specific timeslot in the dossier that generated this order.",
    )
    mcrf_profile_id = fields.Many2one(
        'multi.channel.rental.profile',
        string="Rental Flow Profile",
        copy=False,
    )
    mcrf_source = fields.Selection(
        selection=[
            ('backend', "Backend"),
            ('website', "Website"),
            ('kiosk', "Kiosk"),
        ],
        string="Dossier Source",
        copy=False,
    )

    @api.depends('mcrf_dossier_ids', 'mcrf_dossier_ids.name',
                 'mcrf_dossier_ids.description')
    def _compute_mcrf_dossier_display(self):
        for order in self:
            parts = []
            for d in order.mcrf_dossier_ids:
                if d.description:
                    parts.append(f"{d.name} — {d.description}")
                else:
                    parts.append(d.name)
            order.mcrf_dossier_display = ', '.join(parts) if parts else ''


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    mcrf_dossier_item_id = fields.Many2one(
        'rental.dossier.item',
        string="Dossier Item",
        copy=False,
        help="Dossier item that generated this order line.",
    )
