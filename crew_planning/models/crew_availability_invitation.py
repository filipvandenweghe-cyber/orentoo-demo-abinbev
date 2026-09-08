# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CrewAvailabilityInvitation(models.Model):
    _name = 'crew.availability.invitation'
    _description = 'Crew Availability Invitation'
    _inherit = ['mail.thread']
    _order = 'wave, id'
    _rec_name = 'employee_id'

    request_id = fields.Many2one(
        'crew.availability.request', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one('hr.employee', required=True, index=True)
    company_id = fields.Many2one(related='request_id.company_id', store=True)
    wave = fields.Integer(default=1, required=True)
    channel = fields.Selection([
        ('email', 'Email'),
        ('whatsapp', 'WhatsApp'),
        ('both', 'Email + WhatsApp'),
    ], default='email', required=True)
    state = fields.Selection([
        ('sent', 'Sent'),
        ('reminded', 'Reminded'),
        ('responded', 'Responded'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], default='sent', required=True, tracking=True)
    response = fields.Selection([
        ('pending', 'Pending'),
        ('available', 'Available'),
        ('partial', 'Partial'),
        ('unavailable', 'Unavailable'),
    ], default='pending', required=True, tracking=True)
    response_start = fields.Datetime(string="Available From")
    response_end = fields.Datetime(string="Available To")

    sent_on = fields.Datetime(copy=False)
    last_reminder_on = fields.Datetime(copy=False)
    reminder_count = fields.Integer(default=0, copy=False)

    # convenience (overview)
    work_email = fields.Char(related='employee_id.work_email', string="Email")
    mobile_phone = fields.Char(related='employee_id.mobile_phone', string="Phone")
    availability_mode = fields.Selection(related='employee_id.crew_availability_mode')
    date_start = fields.Datetime(related='request_id.date_start')
    date_end = fields.Datetime(related='request_id.date_end')

    _unique_request_employee = models.Constraint(
        'UNIQUE(request_id, employee_id)',
        'This crew member has already been invited for this request.')

    # ------------------------------------------------------------------
    def _mail_template(self):
        return self.env.ref('crew_planning.mail_template_crew_invitation',
                            raise_if_not_found=False)

    def _send_email(self):
        """Send the email invitation for every record in self (channel-agnostic;
        channel routing happens in _dispatch)."""
        template = self._mail_template()
        for inv in self:
            if template and inv.employee_id.work_email:
                template.send_mail(inv.id, force_send=False)

    def _send_whatsapp(self):
        """Send the WhatsApp nudge via the standard composer when everything is
        configured (account + approved template + phone). Otherwise skip with a
        note on the chatter — never crash the invite (dev has no WA account)."""
        if not self:
            return
        tmpl = self.env.ref('crew_planning.whatsapp_template_crew_invitation',
                            raise_if_not_found=False)
        account = self.env['whatsapp.account'].sudo().search([], limit=1)
        for inv in self:
            phone = inv.employee_id.mobile_phone or inv.employee_id.work_phone
            if not phone:
                continue
            if not (tmpl and account and tmpl.status == 'approved'):
                inv.message_post(body=_(
                    "WhatsApp not sent — configure a WhatsApp account and get the "
                    "invitation template approved first."))
                continue
            try:
                composer = self.env['whatsapp.composer'].with_context(
                    active_model=inv._name, active_ids=inv.ids,
                ).create({
                    'res_model': inv._name,
                    'res_ids': repr(inv.ids),
                    'wa_template_id': tmpl.id,
                })
                composer.action_send_whatsapp_template()
            except Exception as err:  # noqa: BLE001 - resilience, never block the invite
                inv.message_post(body=_("WhatsApp send failed: %s", err))

    def _dispatch(self):
        self.filtered(lambda i: i.channel in ('email', 'both'))._send_email()
        self.filtered(lambda i: i.channel in ('whatsapp', 'both'))._send_whatsapp()

    def action_send_email_now(self):
        """Send an email to these invitees regardless of the stored channel
        (e.g. a follow-up after a WhatsApp, or vice versa)."""
        for inv in self:
            if not inv.employee_id.work_email:
                raise UserError(_("%s has no email address.", inv.employee_id.name))
        self._send_email()

    def action_send_whatsapp_now(self):
        """Send a WhatsApp nudge to these invitees regardless of the stored
        channel (e.g. after an email invitation)."""
        for inv in self:
            if not (inv.employee_id.mobile_phone or inv.employee_id.work_phone):
                raise UserError(_("%s has no phone number.", inv.employee_id.name))
        self._send_whatsapp()

    def action_send(self):
        """(Re)send the initial invitation on its channel(s)."""
        for inv in self:
            inv.sent_on = fields.Datetime.now()
            inv.state = 'sent'
        self._dispatch()

    def action_remind(self):
        """Reminder on an EXISTING invitation — never a new invitation."""
        to_remind = self.filtered(lambda i: i.response == 'pending')
        for inv in to_remind:
            inv.reminder_count += 1
            inv.last_reminder_on = fields.Datetime.now()
            inv.state = 'reminded'
        to_remind._dispatch()

    # ------------------------------------------------------------------
    # Responses — feed the Crew Availability Engine (explicit crew only)
    # ------------------------------------------------------------------
    def _register_engine(self, start, end, available):
        self.ensure_one()
        emp = self.employee_id
        if emp.crew_availability_mode != 'explicit' or not emp.resource_id:
            # Standard-schedule crew: availability follows their working calendar;
            # nothing to punch. We still record the response.
            return
        self.env['crew.availability.engine'].apply_availability(
            emp.resource_id, start, end, available=available,
            origin=self.request_id._origin_code(), employee=emp)

    def action_set_available(self):
        for inv in self:
            inv._register_engine(inv.request_id.date_start, inv.request_id.date_end, True)
            inv.response = 'available'
            inv.state = 'responded'

    def action_set_unavailable(self):
        for inv in self:
            inv._register_engine(inv.request_id.date_start, inv.request_id.date_end, False)
            inv.response = 'unavailable'
            inv.state = 'responded'

    def action_set_partial(self):
        for inv in self:
            if not (inv.response_start and inv.response_end) or inv.response_start >= inv.response_end:
                raise UserError(_(
                    "Set 'Available From' / 'Available To' (within the request "
                    "period) before confirming a partial availability."))
            inv._register_engine(inv.response_start, inv.response_end, True)
            inv.response = 'partial'
            inv.state = 'responded'

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_open_employee(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'res_id': self.employee_id.id,
            'view_mode': 'form',
        }
