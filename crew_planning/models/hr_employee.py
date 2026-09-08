# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    """Crew extension of the employee.

    Requirements:
    - ``is_crew`` marks the schedulable pool and gates the portal.
    - ``crew_availability_mode`` chooses the engine behaviour:
      *standard* = the normal resource calendar / Time Off; *explicit* =
      unavailable-by-default (broad 24/7 calendar + engine-managed leaves),
      used for freelancers who only work when they opt in. Switching modes
      saves/restores the previous working schedule.
    - ``crew_portal_hide_*`` let a planner hide standard portal cards
      (sales/invoices/purchases/projects/tasks/timesheets/subscriptions/
      signatures) per crew member; ``_crew_portal_hidden_counters`` maps those
      flags to the home-counter keys the portal zeroes to hide each card.
    - ``action_crew_grant_portal`` provisions portal access for the crew
      member's linked user.
    """
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
    crew_portal_hide_sales = fields.Boolean(string="Hide Sales Orders")
    crew_portal_hide_invoices = fields.Boolean(string="Hide Invoices")
    crew_portal_hide_purchases = fields.Boolean(string="Hide Purchases")
    crew_portal_hide_projects = fields.Boolean(string="Hide Projects")
    crew_portal_hide_tasks = fields.Boolean(string="Hide Tasks")
    crew_portal_hide_timesheets = fields.Boolean(string="Hide Timesheets")
    crew_portal_hide_subscriptions = fields.Boolean(string="Hide Subscriptions")
    crew_portal_hide_signatures = fields.Boolean(string="Hide Signatures")

    # field name -> portal home counter keys to zero (hides the card)
    _CREW_PORTAL_HIDE_MAP = {
        'crew_portal_hide_sales': {'order_count', 'quotation_count'},
        'crew_portal_hide_invoices': {'invoice_count', 'bill_count', 'overdue_invoice_count'},
        'crew_portal_hide_purchases': {'purchase_count', 'rfq_count'},
        'crew_portal_hide_projects': {'project_count'},
        'crew_portal_hide_tasks': {'task_count'},
        'crew_portal_hide_timesheets': {'timesheet_count'},
        'crew_portal_hide_subscriptions': {'subscription_count'},
        'crew_portal_hide_signatures': {'sign_count', 'to_sign_count'},
    }

    def _crew_portal_hidden_counters(self):
        """Portal home counter keys to force to 0 for this crew member so the
        corresponding cards are hidden."""
        self.ensure_one()
        keys = set()
        for field_name, counter_keys in self._CREW_PORTAL_HIDE_MAP.items():
            if self[field_name]:
                keys |= counter_keys
        return keys
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

    def action_crew_grant_portal(self):
        """One-click: create (or reuse) a Portal user for this crew member and
        link it as the employee's Related User, so they can use the Crew
        Portal. Sends the standard set-password invitation."""
        self.ensure_one()
        if self.user_id:
            raise UserError(_(
                "%s already has a related user (%s).", self.name, self.user_id.login))
        if not self.work_email:
            raise UserError(_("Set the employee's Work Email before granting portal access."))
        Users = self.env['res.users'].sudo()
        partner = self.work_contact_id
        if not partner:
            partner = self.env['res.partner'].sudo().create({
                'name': self.name, 'email': self.work_email})
            self.work_contact_id = partner
        elif not partner.email:
            partner.email = self.work_email
        user = Users.with_context(active_test=False).search(
            [('login', '=', self.work_email)], limit=1)
        if not user:
            user = Users.create({
                'name': self.name,
                'login': self.work_email,
                'email': self.work_email,
                'partner_id': partner.id,
                'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
            })
        self.user_id = user.id
        try:
            user.action_reset_password()
        except Exception:  # noqa: BLE001 - no mail server in dev; user is still created
            pass
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
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
