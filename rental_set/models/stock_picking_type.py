from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    rental_incoming_policy = fields.Selection(
        selection=[
            ('projected', 'Projected only'),
            ('operational', 'Operational (raises booking availability)'),
            ('ignore', 'Ignore'),
        ],
        string='Rental Availability Policy',
        default='projected',
        help=(
            "How confirmed, not-yet-done INCOMING stock received through this "
            "operation type affects rental availability — grounded on the "
            "move's scheduled arrival date:\n\n"
            "• Projected only (default): shown in the projected view but never "
            "raises the operational booking number. The safe default for "
            "uncertain external supply (purchases, manufacturing).\n"
            "• Operational: raises the operational rental availability once the "
            "units are guaranteed present for the whole interval. Use for "
            "supply you trust enough to promise against (reliable POs, "
            "intercompany supply).\n"
            "• Ignore: excluded entirely.\n\n"
            "Note: relocations of stock you already own (interwarehouse / "
            "intercompany transfers) count operationally by default — set this "
            "to Ignore to opt them out."
        ),
    )
