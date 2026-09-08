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
    crew_unavailable_reported = fields.Boolean(
        string="Crew Reported Unavailable", copy=False,
        help="The assigned crew member reported they can no longer perform this "
             "shift. The assignment is kept until the planner handles it.")
    crew_unavailable_reason = fields.Char(string="Reason", copy=False)

    def action_crew_report_cannot_work(self, reason=False):
        """Crew reports they can no longer perform this shift. Flag it and
        notify the planner — never silently remove the assignment (§7/§12)."""
        for slot in self:
            slot.crew_unavailable_reported = True
            if reason:
                slot.crew_unavailable_reason = reason
            body = _(
                "%(emp)s reported they can no longer work the shift %(start)s → %(end)s.",
                emp=slot.employee_id.display_name or _("Crew member"),
                start=slot.start_datetime, end=slot.end_datetime)
            if reason:
                body += _(" Reason: %s", reason)
            if slot.crew_request_id:
                slot.crew_request_id.message_post(body=body)
        return True

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
