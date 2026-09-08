# -*- coding: utf-8 -*-
from odoo import fields, models


class ResourceCalendarLeaves(models.Model):
    """Leaves are the single operational source of (un)availability. This adds
    the ``crew_managed`` marker so the Crew Availability Engine only ever
    rewrites the leaves it compiled itself — Time Off and other standard leaves
    are never touched."""
    _inherit = 'resource.calendar.leaves'

    # Marks the unavailability intervals maintained by the Crew Availability
    # Engine (compiled from registered availability + the rolling horizon).
    # The engine only ever touches leaves with this flag set, so Time Off and
    # other standard leaves are never affected.
    crew_managed = fields.Boolean(
        string="Crew-managed",
        default=False,
        index=True,
        copy=False,
        help="Set automatically for unavailability intervals maintained by the "
             "Crew Availability Engine. Not edited by hand.",
    )
