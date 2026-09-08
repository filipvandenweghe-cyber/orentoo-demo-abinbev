# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CrewEnterAvailability(models.TransientModel):
    """Backend action for a planner to register availability on behalf of a
    crew member (e.g. confirmed by phone/WhatsApp). Manipulates the SAME
    standard resource availability via the Crew Availability Engine."""
    _name = 'crew.enter.availability'
    _description = 'Enter Crew Availability'

    employee_id = fields.Many2one('hr.employee', required=True)
    resource_id = fields.Many2one(
        related='employee_id.resource_id', readonly=True)
    availability_mode = fields.Selection(
        related='employee_id.crew_availability_mode', readonly=True)
    date_start = fields.Datetime(required=True)
    date_end = fields.Datetime(required=True)
    state = fields.Selection([
        ('available', 'Available'),
        ('unavailable', 'Unavailable'),
    ], required=True, default='available')

    def action_apply(self):
        self.ensure_one()
        if self.date_start >= self.date_end:
            raise UserError(_("Start must be before end."))
        if not self.resource_id:
            raise UserError(_("This employee has no resource."))
        if self.availability_mode != 'explicit':
            raise UserError(_(
                "%s uses a Standard Working Schedule. Explicit availability "
                "only applies to Explicit-Availability crew.", self.employee_id.name))
        self.env['crew.availability.engine'].apply_availability(
            self.resource_id, self.date_start, self.date_end,
            available=(self.state == 'available'),
            origin='planner', employee=self.employee_id)
        return {'type': 'ir.actions.act_window_close'}
