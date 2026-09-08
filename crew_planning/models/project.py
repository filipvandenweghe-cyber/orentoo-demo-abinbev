# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    crew_request_ids = fields.One2many(
        'crew.availability.request', 'project_id', string="Availability Requests")
    crew_request_count = fields.Integer(compute='_compute_crew_request_count')

    @api.depends('crew_request_ids')
    def _compute_crew_request_count(self):
        data = {}
        if self.ids:
            for grp in self.env['crew.availability.request']._read_group(
                    [('project_id', 'in', self.ids)], ['project_id'], ['__count']):
                data[grp[0].id] = grp[1]
        for project in self:
            project.crew_request_count = data.get(project.id, 0)

    def action_crew_availability_request(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Availability Request"),
            'res_model': 'crew.availability.request',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_request_type': 'project',
                'default_project_id': self.id,
                'default_date_start': self.date_start,
                'default_date_end': self.date,
            },
        }

    def action_view_crew_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Availability Requests"),
            'res_model': 'crew.availability.request',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_request_type': 'project',
                        'default_project_id': self.id},
        }


class ProjectTask(models.Model):
    _inherit = 'project.task'

    crew_request_ids = fields.One2many(
        'crew.availability.request', 'task_id', string="Availability Requests")
    crew_request_count = fields.Integer(compute='_compute_crew_request_count')
    planning_slot_ids = fields.One2many(
        'planning.slot', 'task_id', string="Shifts")
    planning_slot_count = fields.Integer(compute='_compute_planning_slot_count')

    @api.depends('crew_request_ids')
    def _compute_crew_request_count(self):
        data = {}
        if self.ids:
            for grp in self.env['crew.availability.request']._read_group(
                    [('task_id', 'in', self.ids)], ['task_id'], ['__count']):
                data[grp[0].id] = grp[1]
        for task in self:
            task.crew_request_count = data.get(task.id, 0)

    def _compute_planning_slot_count(self):
        data = dict(self.env['planning.slot']._read_group(
            [('task_id', 'in', self.ids)], ['task_id'], ['__count']))
        for task in self:
            task.planning_slot_count = data.get(task, 0)

    def action_crew_schedule_shift(self):
        """Open a new, prefilled Planning shift form for this task. The planner
        picks the crew member (resource) and saves."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Schedule Shift"),
            'res_model': 'planning.slot',
            'view_mode': 'form',
            'views': [(self.env.ref('planning.planning_view_form').id, 'form')],
            'target': 'current',
            'context': {
                'default_task_id': self.id,
                'default_project_id': self.project_id.id,
                'default_sale_line_id': self.sale_line_id.id,
                'default_start_datetime': self.planned_date_begin,
                'default_end_datetime': self.date_deadline,
                'default_allocated_hours': self.allocated_hours,
            },
        }

    def action_view_planning_slots(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Shifts"),
            'res_model': 'planning.slot',
            'view_mode': 'list,form',
            'domain': [('task_id', '=', self.id)],
            'context': {
                'default_task_id': self.id,
                'default_project_id': self.project_id.id,
                'default_sale_line_id': self.sale_line_id.id,
            },
        }

    def action_crew_availability_request(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Availability Request"),
            'res_model': 'crew.availability.request',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_request_type': 'task',
                'default_task_id': self.id,
                'default_project_id': self.project_id.id,
                'default_date_start': self.planned_date_begin,
                'default_date_end': self.date_deadline,
                'default_indicative_hours': self.allocated_hours,
            },
        }

    def action_view_crew_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Availability Requests"),
            'res_model': 'crew.availability.request',
            'view_mode': 'list,form',
            'domain': [('task_id', '=', self.id)],
            'context': {'default_request_type': 'task',
                        'default_task_id': self.id,
                        'default_project_id': self.project_id.id},
        }
