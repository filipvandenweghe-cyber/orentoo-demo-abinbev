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

    @api.constrains('date_start', 'date_end')
    def _check_period(self):
        for rec in self:
            if rec.date_start >= rec.date_end:
                raise ValidationError(_(
                    "Availability start must be before its end."))
