# -*- coding: utf-8 -*-
from odoo import fields, models


class CrewAvailabilityLog(models.Model):
    """Append-only audit of availability declarations: what was communicated,
    by whom, from where. Availability *knowledge*, never the staffing source."""
    _name = 'crew.availability.log'
    _description = 'Crew Availability Log'
    _order = 'create_date desc, id desc'

    employee_id = fields.Many2one('hr.employee', index=True, ondelete='set null')
    resource_id = fields.Many2one('resource.resource', index=True, ondelete='set null')
    company_id = fields.Many2one('res.company', index=True)
    date_start = fields.Datetime(required=True)
    date_end = fields.Datetime(required=True)
    declared_state = fields.Selection([
        ('available', 'Available'),
        ('unavailable', 'Unavailable'),
    ], required=True)
    origin = fields.Selection([
        ('self_portal', 'Self-service portal'),
        ('task_request', 'Task availability request'),
        ('project_request', 'Project availability request'),
        ('period_request', 'Period availability request'),
        ('planner', 'Entered by planner'),
        ('system', 'System'),
    ], required=True, default='planner', index=True)
    project_id = fields.Many2one('project.project', ondelete='set null')
    task_id = fields.Many2one('project.task', ondelete='set null')
    user_id = fields.Many2one(
        'res.users', string='Changed by', default=lambda self: self.env.user, index=True)
