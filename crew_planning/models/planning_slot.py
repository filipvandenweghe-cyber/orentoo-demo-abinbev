# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PlanningSlot(models.Model):
    _inherit = 'planning.slot'

    # §14 — one operational Planning Shift represents one Task. Standard Odoo 19
    # planning.slot has project_id/sale_line_id but NOT task_id, so we add it.
    task_id = fields.Many2one(
        'project.task', string="Task",
        domain="[('project_id', '=?', project_id)]",
        index='btree_not_null')
    crew_request_id = fields.Many2one(
        'crew.availability.request', string="Availability Request",
        index='btree_not_null', copy=False,
        help="Availability request this shift staffs (for coverage/staffing KPIs).")

    @api.onchange('task_id')
    def _onchange_task_id(self):
        if self.task_id:
            self.project_id = self.task_id.project_id

    @api.constrains('task_id', 'project_id')
    def _check_task_in_project(self):
        for slot in self:
            if slot.task_id and slot.project_id and slot.task_id.project_id != slot.project_id:
                raise ValidationError(_(
                    "The task %(task)s does not belong to project %(project)s.",
                    task=slot.task_id.display_name,
                    project=slot.project_id.display_name))
