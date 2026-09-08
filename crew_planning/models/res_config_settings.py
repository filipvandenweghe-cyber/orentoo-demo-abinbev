# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    """Crew planning configuration: the rolling unavailability coverage horizon
    (how far ahead Explicit-Availability crew are guaranteed blanket-unavailable)
    and the availability entry horizon (how far ahead crew may register
    availability). The self-unassign policy itself is the standard Planning
    setting, reused as-is."""
    _inherit = 'res.config.settings'

    crew_unavailability_horizon_months = fields.Integer(
        string="Unavailability Coverage Horizon (months)",
        config_parameter='crew_planning.unavailability_horizon_months',
        default=12,
        help="How far ahead the rolling blanket unavailability is guaranteed "
             "for Explicit-Availability crew.")
    crew_availability_entry_horizon_months = fields.Integer(
        string="Availability Entry Horizon (months)",
        config_parameter='crew_planning.availability_entry_horizon_months',
        default=6,
        help="How far ahead a crew member may register availability. Must not "
             "exceed the unavailability coverage horizon.")

    @api.constrains('crew_unavailability_horizon_months',
                    'crew_availability_entry_horizon_months')
    def _check_crew_horizons(self):
        for rec in self:
            if rec.crew_availability_entry_horizon_months > rec.crew_unavailability_horizon_months:
                raise ValidationError(_(
                    "The Availability Entry Horizon (%s) may not exceed the "
                    "Unavailability Coverage Horizon (%s).",
                    rec.crew_availability_entry_horizon_months,
                    rec.crew_unavailability_horizon_months))
