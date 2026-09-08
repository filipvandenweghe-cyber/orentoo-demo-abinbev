# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

RESP_LABELS = {
    'pending': 'pending',
    'available': 'available',
    'partial': 'partial',
    'unavailable': 'unavailable',
}


class CrewInviteWizard(models.TransientModel):
    """Transient candidate selection. Shows every matching crew member with
    their status (new / already invited / already known available/unavailable).
    On confirm: NEW people are invited (and emailed/WhatsApp'd); people whose
    availability we already KNOW are just counted on the request (no message
    sent); already-invited people are left untouched."""
    _name = 'crew.invite.wizard'
    _description = 'Crew — Find & Invite Candidates'

    request_id = fields.Many2one('crew.availability.request', required=True)
    channel = fields.Selection([
        ('email', 'Email'),
        ('whatsapp', 'WhatsApp'),
        ('both', 'Email + WhatsApp'),
    ], default='email', required=True)
    next_wave = fields.Integer(readonly=True)
    line_ids = fields.One2many('crew.invite.wizard.line', 'wizard_id', string="Candidates")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        request_id = res.get('request_id') or self.env.context.get('default_request_id')
        if request_id:
            request = self.env['crew.availability.request'].browse(request_id)
            res['next_wave'] = max(request.invitation_ids.mapped('wave'), default=0) + 1
            res['line_ids'] = self._build_lines(request)
        return res

    def _build_lines(self, request):
        # Show ALL matching crew (do not exclude invited or answered).
        emps = request._match_candidate_employees(
            exclude_answered=False, exclude_invited=False)
        inv_by_emp = {inv.employee_id.id: inv for inv in request.invitation_ids}
        cmds = []
        for emp in emps:
            inv = inv_by_emp.get(emp.id)
            if inv:
                cmds.append((0, 0, {
                    'employee_id': emp.id,
                    'already_invited': True,
                    'invitation_response': inv.response,
                    'known_state': inv.response if inv.response in ('available', 'unavailable') else 'unknown',
                }))
            else:
                cmds.append((0, 0, {
                    'employee_id': emp.id,
                    'already_invited': False,
                    'known_state': request._employee_known_state(emp),
                }))
        return cmds

    def action_refresh(self):
        self.ensure_one()
        self.next_wave = max(self.request_id.invitation_ids.mapped('wave'), default=0) + 1
        self.line_ids = [(5, 0, 0)] + self._build_lines(self.request_id)
        return self._reopen()

    def action_select_all(self):
        # Only the actionable ones (not already invited).
        self.line_ids.filtered(lambda l: not l.already_invited).selected = True
        return self._reopen()

    def action_invite_selected(self):
        self.ensure_one()
        selected = self.line_ids.filtered(lambda l: l.selected and l.employee_id)
        if not selected:
            raise UserError(_("Please select at least one crew member."))
        new_lines = selected.filtered(
            lambda l: not l.already_invited and l.known_state == 'unknown')
        known_lines = selected.filtered(
            lambda l: not l.already_invited
            and l.known_state in ('available', 'partial', 'unavailable'))
        if not new_lines and not known_lines:
            raise UserError(_(
                "The selected crew are already invited — nothing to add."))

        # Contact details are only required for people we actually message
        # (the NEW ones); already-known people are just counted, never messaged.
        if new_lines and self.channel in ('email', 'both'):
            missing = new_lines.filtered(lambda l: not l.employee_id.work_email)
            if missing:
                names = "\n".join("- %s" % l.employee_id.name for l in missing)
                raise UserError(_(
                    "These crew members have no email address and cannot be "
                    "invited by email. Add a work email, or unselect them:\n%s", names))
        if new_lines and self.channel in ('whatsapp', 'both'):
            missing = new_lines.filtered(
                lambda l: not (l.employee_id.mobile_phone or l.employee_id.work_phone))
            if missing:
                names = "\n".join("- %s" % l.employee_id.name for l in missing)
                raise UserError(_(
                    "These crew members have no phone number and cannot be "
                    "invited by WhatsApp. Add a phone, or unselect them:\n%s", names))

        Invitation = self.env['crew.availability.invitation']
        wave = max(self.request_id.invitation_ids.mapped('wave'), default=0) + 1

        # Already-known people: recorded on the request to keep the count
        # correct, WITHOUT sending anything (and without touching the engine —
        # their availability already exists).
        for line in known_lines:
            Invitation.create({
                'request_id': self.request_id.id,
                'employee_id': line.employee_id.id,
                'wave': wave,
                'channel': self.channel,
                'response': line.known_state,
                'state': 'responded',
            })

        # New people: real invitations that get sent on the chosen channel.
        sent = Invitation
        for line in new_lines:
            sent |= Invitation.create({
                'request_id': self.request_id.id,
                'employee_id': line.employee_id.id,
                'wave': wave,
                'channel': self.channel,
            })
        sent.action_send()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crew.availability.request',
            'res_id': self.request_id.id,
            'view_mode': 'form',
        }

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crew.invite.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class CrewInviteWizardLine(models.TransientModel):
    _name = 'crew.invite.wizard.line'
    _description = 'Crew — Candidate Line'

    wizard_id = fields.Many2one('crew.invite.wizard', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee')
    selected = fields.Boolean()
    work_email = fields.Char(related='employee_id.work_email')
    mobile_phone = fields.Char(related='employee_id.mobile_phone')
    availability_mode = fields.Selection(related='employee_id.crew_availability_mode')
    already_invited = fields.Boolean()
    invitation_response = fields.Char()
    known_state = fields.Selection([
        ('unknown', 'Unknown'),
        ('available', 'Available'),
        ('partial', 'Partial'),
        ('unavailable', 'Unavailable'),
    ], default='unknown')
    status_label = fields.Char(compute='_compute_status_label')

    @api.depends('already_invited', 'invitation_response', 'known_state')
    def _compute_status_label(self):
        for line in self:
            if line.already_invited:
                resp = line.invitation_response or 'pending'
                line.status_label = _("Invited — %s", RESP_LABELS.get(resp, resp))
            elif line.known_state == 'available':
                line.status_label = _("Available (not invited)")
            elif line.known_state == 'partial':
                line.status_label = _("Partially available (not invited)")
            elif line.known_state == 'unavailable':
                line.status_label = _("Unavailable (not invited)")
            else:
                line.status_label = _("New")
