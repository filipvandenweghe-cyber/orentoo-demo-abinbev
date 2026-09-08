# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CrewAvailability(models.Model):
    """Registered POSITIVE availability windows for a crew resource.

    This is the editable *compile source* for the Crew Availability Engine — it
    is compiled into standard ``resource.calendar.leaves`` (the holes in the
    blanket unavailability). It is **never read by staffing / Auto-Plan**; the
    authoritative operational availability is standard Odoo resource
    availability. Kept minimal on purpose.
    """
    _name = 'crew.availability'
    _description = 'Crew Availability Window'
    _order = 'date_start'

    resource_id = fields.Many2one(
        'resource.resource', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one('hr.employee', index=True)
    company_id = fields.Many2one('res.company', index=True)
    date_start = fields.Datetime(required=True)
    date_end = fields.Datetime(required=True)

    @api.depends('employee_id', 'resource_id', 'date_start', 'date_end')
    def _compute_display_name(self):
        for rec in self:
            who = rec.employee_id.name or rec.resource_id.name or _("Availability")
            if rec.date_start and rec.date_end:
                start = fields.Datetime.context_timestamp(rec, rec.date_start)
                end = fields.Datetime.context_timestamp(rec, rec.date_end)
                same_day = start.date() == end.date()
                end_fmt = '%H:%M' if same_day else '%d/%m %H:%M'
                rec.display_name = _("%(who)s — available %(start)s → %(end)s", who=who,
                                     start=start.strftime('%d/%m %H:%M'),
                                     end=end.strftime(end_fmt))
            else:
                rec.display_name = who

    @api.constrains('date_start', 'date_end')
    def _check_period(self):
        for rec in self:
            if rec.date_start >= rec.date_end:
                raise ValidationError(_(
                    "Availability start must be before its end."))
