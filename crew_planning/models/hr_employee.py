# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    is_crew = fields.Boolean(
        string="Crew Member",
        help="This employee is part of the schedulable crew pool.")
    crew_availability_mode = fields.Selection([
        ('standard', 'Standard Working Schedule'),
        ('explicit', 'Explicit Availability'),
    ], string="Availability Mode", default='standard', required=True, tracking=True,
        help="Standard Working Schedule: normal Odoo resource calendar / Time Off.\n"
             "Explicit Availability: unavailable unless availability has been "
             "explicitly registered (broad 24/7 calendar + managed leaves).")
    crew_saved_calendar_id = fields.Many2one(
        'resource.calendar', copy=False,
        help="Working schedule to restore when leaving Explicit Availability mode.")
    crew_availability_ids = fields.One2many(
        'crew.availability', 'employee_id', string="Availability Windows")
    crew_availability_count = fields.Integer(compute='_compute_crew_counts')

    @api.depends('crew_availability_ids')
    def _compute_crew_counts(self):
        data = {}
        if self.ids:
            for group in self.env['crew.availability']._read_group(
                    [('employee_id', 'in', self.ids)], ['employee_id'], ['__count']):
                data[group[0].id] = group[1]
        for emp in self:
            emp.crew_availability_count = data.get(emp.id, 0)

    # ------------------------------------------------------------------
    # Keep the Crew Availability Engine in sync with the mode
    # ------------------------------------------------------------------
    def _sync_crew_mode(self, previous_modes=None):
        engine = self.env['crew.availability.engine']
        for emp in self:
            if emp.crew_availability_mode == 'explicit':
                engine._enable_explicit(emp)
            elif previous_modes is None or previous_modes.get(emp.id) == 'explicit':
                engine._disable_explicit(emp)

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        employees.filtered(
            lambda e: e.crew_availability_mode == 'explicit'
        ).with_context(crew_skip_sync=True)._sync_crew_mode()
        return employees

    def write(self, vals):
        previous = {e.id: e.crew_availability_mode for e in self} \
            if 'crew_availability_mode' in vals else None
        res = super().write(vals)
        if 'crew_availability_mode' in vals and not self.env.context.get('crew_skip_sync'):
            self.with_context(crew_skip_sync=True)._sync_crew_mode(previous)
        return res

    def action_crew_enter_availability(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Enter Availability"),
            'res_model': 'crew.enter.availability',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_employee_id': self.id},
        }

    def action_view_crew_availability(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Availability — %s", self.name),
            'res_model': 'crew.availability',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id,
                        'default_resource_id': self.resource_id.id},
        }
