# -*- coding: utf-8 -*-
from odoo import _, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

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


class ProjectTask(models.Model):
    _inherit = 'project.task'

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
