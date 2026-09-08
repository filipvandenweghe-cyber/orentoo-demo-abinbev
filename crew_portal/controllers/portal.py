# -*- coding: utf-8 -*-
from datetime import datetime

import pytz

from odoo import _, fields, http
from odoo.http import request
from odoo.tools import format_datetime
from odoo.addons.portal.controllers.portal import CustomerPortal


class CrewPortal(CustomerPortal):
    """Own-records-only crew self-service. Every route resolves the logged-in
    user's employee and reads/writes ONLY that person's data (sudo is used for
    the controlled writes, but always scoped to the resolved employee)."""

    # ------------------------------------------------------------------
    def _crew_employee(self):
        return request.env['hr.employee'].sudo().search(
            [('user_id', '=', request.env.user.id)], limit=1)

    def _fmt_dt(self, value):
        """Localized datetime with the month spelled out, in the user's tz."""
        if not value:
            return ''
        return format_datetime(request.env, value, tz=request.env.user.tz or 'UTC',
                               dt_format='d MMMM y HH:mm')

    def _parse_portal_dt(self, value):
        """A browser datetime-local value ('YYYY-MM-DDTHH:MM') is naive local
        time; convert it to the naive UTC datetimes Odoo stores."""
        if not value:
            return False
        naive = datetime.strptime(value.replace('T', ' ')[:16], '%Y-%m-%d %H:%M')
        tz = pytz.timezone(request.env.user.tz or 'UTC')
        return tz.localize(naive).astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        emp = self._crew_employee()
        if 'crew_availability_count' in counters:
            values['crew_availability_count'] = request.env['crew.availability'].sudo().search_count(
                [('employee_id', '=', emp.id)]) if emp else 0
        if 'crew_planning_count' in counters:
            values['crew_planning_count'] = request.env['planning.slot'].sudo().search_count(
                [('resource_id', '=', emp.resource_id.id),
                 ('end_datetime', '>=', fields.Datetime.now())]
            ) if emp and emp.resource_id else 0
        # Hide configured portal cards for this crew member by zeroing their
        # counters (a 0-count card is hidden on the portal home).
        if emp:
            for key in emp._crew_portal_hidden_counters():
                if key in values:
                    values[key] = 0
        return values

    # ------------------------------------------------------------------
    # My Availability
    # ------------------------------------------------------------------
    @http.route(['/my/availability'], type='http', auth='user', website=True)
    def portal_my_availability(self, **kw):
        emp = self._crew_employee()
        if not emp:
            return request.render('crew_portal.portal_not_crew', {'page_name': 'crew'})
        windows = request.env['crew.availability'].sudo().search(
            [('employee_id', '=', emp.id)], order='date_start')
        today = fields.Date.context_today(request.env.user)
        invitations = request.env['crew.availability.invitation'].sudo().search(
            [('employee_id', '=', emp.id), ('response', '=', 'pending')]
        ).filtered(
            lambda i: i.request_id.date_start and i.request_id.date_start.date() >= today
        ).sorted(lambda i: i.request_id.date_start)  # chronological by start date
        win_rows = [{
            'id': w.id,
            'start': self._fmt_dt(w.date_start),
            'end': self._fmt_dt(w.date_end),
        } for w in windows]
        inv_rows = [{
            'id': inv.id,
            'header': (inv.request_id.task_id.display_name
                       or inv.request_id.project_id.display_name
                       or inv.request_id.name or _("Availability request")),
            'period': inv.request_id.period_label,
            'posted': self._fmt_dt(inv.sent_on or inv.create_date),
            'indicative_hours': inv.request_id.indicative_hours,
            'planning_id': inv.request_id.name,
        } for inv in invitations]
        return request.render('crew_portal.portal_my_availability', {
            'page_name': 'crew_availability',
            'employee': emp,
            'win_rows': win_rows,
            'inv_rows': inv_rows,
        })

    @http.route(['/my/availability/register'], type='http', auth='user',
                methods=['POST'], website=True)
    def portal_register_availability(self, **post):
        emp = self._crew_employee()
        start = self._parse_portal_dt(post.get('date_start'))
        end = self._parse_portal_dt(post.get('date_end'))
        if emp and emp.resource_id and start and end and start < end:
            request.env['crew.availability.engine'].sudo().apply_availability(
                emp.resource_id.sudo(), start, end,
                available=(post.get('state', 'available') == 'available'),
                origin='self_portal', employee=emp, enforce_entry_horizon=True)
        return request.redirect('/my/availability')

    @http.route(['/my/availability/window/<int:window_id>/remove'], type='http',
                auth='user', methods=['POST'], website=True)
    def portal_remove_availability(self, window_id, **post):
        emp = self._crew_employee()
        window = request.env['crew.availability'].sudo().browse(window_id)
        if emp and window.exists() and window.employee_id.id == emp.id:
            resource = window.resource_id
            window.unlink()
            request.env['crew.availability.engine'].sudo()._recompile(resource)
        return request.redirect('/my/availability')

    @http.route(['/my/invitation/<int:inv_id>/respond'], type='http', auth='user',
                methods=['POST'], website=True)
    def portal_respond_invitation(self, inv_id, **post):
        emp = self._crew_employee()
        inv = request.env['crew.availability.invitation'].sudo().browse(inv_id)
        if emp and inv.exists() and inv.employee_id.id == emp.id:
            if post.get('response') == 'available':
                inv.action_set_available()
            elif post.get('response') == 'unavailable':
                inv.action_set_unavailable()
        return request.redirect('/my/availability')

    # ------------------------------------------------------------------
    # My Planning
    # ------------------------------------------------------------------
    @http.route(['/my/planning'], type='http', auth='user', website=True)
    def portal_my_planning(self, **kw):
        emp = self._crew_employee()
        if not emp:
            return request.render('crew_portal.portal_not_crew', {'page_name': 'crew'})
        Slot = request.env['planning.slot'].sudo()
        slots = Slot.search([
            ('resource_id', '=', emp.resource_id.id),
            ('end_datetime', '>=', fields.Datetime.now()),
        ], order='start_datetime') if emp.resource_id else Slot.browse()
        return request.render('crew_portal.portal_my_planning', {
            'page_name': 'crew_planning',
            'employee': emp,
            'slots': slots,
        })

    @http.route(['/my/planning/<int:slot_id>/cannot-work'], type='http', auth='user',
                methods=['POST'], website=True)
    def portal_cannot_work(self, slot_id, **post):
        emp = self._crew_employee()
        slot = request.env['planning.slot'].sudo().browse(slot_id)
        if emp and slot.exists() and slot.resource_id.employee_id.id == emp.id:
            slot.action_crew_report_cannot_work(post.get('reason'))
        return request.redirect('/my/planning')
