from odoo import fields, models


class RentalFlowHeroImage(models.Model):
    """Hero/carousel images for the kiosk start page."""

    _name = 'multi.channel.rental.hero.image'
    _description = 'Kiosk Hero Image'
    _order = 'sequence, id'

    profile_id = fields.Many2one(
        'multi.channel.rental.profile',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(required=True, translate=True)
    image = fields.Image(
        required=True,
        max_width=1920,
        max_height=1080,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
