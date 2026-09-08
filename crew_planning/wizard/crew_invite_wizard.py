# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CrewInviteWizard(models.TransientModel):
    """Transient candidate selection. Matching a candidate does NOT create an
    invitation — only *Invite Selected* does. Re-opening excludes everyone
    already invited for the request (waves)."""
    _name = 'crew.invite.wizard'
    _description = 'Crew — Find & Invite Candidates'

    request_id = fields.Many2one('crew.availability.request', required=True)
    exclude_answered = fields.Boolean(
        string="Skip already-answered", default=True,
        help="Exclude crew who already have known availability for this period, "
             "so we don't ask them again.")
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
            res['next_wave'] = (max(request.invitation_ids.mapped('wave'), default=0)) + 1
            res['line_ids'] = self._build_lines(request, res.get('exclude_answered', True))
        return res

    def _build_lines(self, request, exclude_answered):
        emps = request._match_candidate_employees(exclude_answered=exclude_answered)
        return [(0, 0, {
            'employee_id': e.id,
            'selected': False,
        }) for e in emps]

    def action_refresh(self):
        self.ensure_one()
        self.line_ids = [(5, 0, 0)] + self._build_lines(self.request_id, self.exclude_answered)
        return self._reopen()

    def action_select_all(self):
        self.line_ids.selected = True
        return self._reopen()

    def action_invite_selected(self):
        self.ensure_one()
        selected = self.line_ids.filtered('selected')
        if not selected:
            raise UserError(_("Please select at least one crew member to invite."))
        Invitation = self.env['crew.availability.invitation']
        wave = max(self.request_id.invitation_ids.mapped('wave'), default=0) + 1
        created = Invitation
        for line in selected:
            inv = Invitation.create({
                'request_id': self.request_id.id,
                'employee_id': line.employee_id.id,
                'wave': wave,
                'channel': self.channel,
            })
            created |= inv
        created.action_send()
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
    employee_id = fields.Many2one('hr.employee', required=True)
    selected = fields.Boolean()
    work_email = fields.Char(related='employee_id.work_email')
    mobile_phone = fields.Char(related='employee_id.mobile_phone')
    availability_mode = fields.Selection(related='employee_id.crew_availability_mode')
