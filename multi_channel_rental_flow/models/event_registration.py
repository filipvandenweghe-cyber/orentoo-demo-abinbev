from odoo import fields, models

# Business requirements: EV01–EV08, SD01
# See __init__.py for full index.


class EventRegistration(models.Model):
    _inherit = 'event.registration'

    mcrf_dossier_id = fields.Many2one(
        'rental.dossier',
        string="Rental Dossier",
        copy=False,
        index=True,
        help="Dossier that created this event registration.",
    )
    mcrf_dossier_item_id = fields.Many2one(
        'rental.dossier.item',
        string="Dossier Item",
        copy=False,
    )
