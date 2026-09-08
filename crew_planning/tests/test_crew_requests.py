# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'crew_planning')
class TestCrewRequests(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = cls.env['crew.availability.engine']
        cls.now = cls.engine._now()

        # Skills: one type "Sound" with 3 ordered levels
        cls.skill_type = cls.env['hr.skill.type'].create({'name': 'Audio'})
        cls.lvl_beg, cls.lvl_int, cls.lvl_adv = cls.env['hr.skill.level'].create([
            {'name': 'Beginner', 'level_progress': 0, 'skill_type_id': cls.skill_type.id},
            {'name': 'Intermediate', 'level_progress': 50, 'skill_type_id': cls.skill_type.id},
            {'name': 'Advanced', 'level_progress': 100, 'skill_type_id': cls.skill_type.id},
        ])
        cls.skill_sound = cls.env['hr.skill'].create({
            'name': 'Sound', 'skill_type_id': cls.skill_type.id})
        cls.skill_light = cls.env['hr.skill'].create({
            'name': 'Lighting', 'skill_type_id': cls.skill_type.id})

        cls.role_sound = cls.env['planning.role'].create({'name': 'Sound Tech'})

        cls.emp_adv = cls._make_emp('Ava Advanced', 'explicit', cls.skill_sound, cls.lvl_adv, cls.role_sound)
        cls.emp_int = cls._make_emp('Ivo Intermediate', 'standard', cls.skill_sound, cls.lvl_int, cls.role_sound)
        cls.emp_light = cls._make_emp('Lena Lighting', 'standard', cls.skill_light, cls.lvl_adv, cls.role_sound)

        cls.d1 = cls.now + timedelta(days=20)
        cls.d2 = cls.d1 + timedelta(hours=10)

    @classmethod
    def _make_emp(cls, name, mode, skill, level, role):
        emp = cls.env['hr.employee'].create({
            'name': name, 'is_crew': True, 'crew_availability_mode': mode})
        cls.env['hr.employee.skill'].create({
            'employee_id': emp.id,
            'skill_type_id': skill.skill_type_id.id,
            'skill_id': skill.id,
            'skill_level_id': level.id,
        })
        emp.resource_id.default_role_id = role
        return emp

    def _make_request(self, **kw):
        vals = {
            'request_type': 'period',
            'date_start': self.d1,
            'date_end': self.d2,
            'headcount_needed': 1,
            'skill_requirement_ids': [(0, 0, {
                'skill_type_id': self.skill_type.id,
                'skill_id': self.skill_sound.id,
                'min_skill_level_id': self.lvl_int.id,
            })],
        }
        vals.update(kw)
        return self.env['crew.availability.request'].create(vals)

    def _wizard(self, req, exclude_answered=True):
        wiz = self.env['crew.invite.wizard'].create({
            'request_id': req.id, 'exclude_answered': exclude_answered})
        wiz.action_refresh()
        return wiz

    # ------------------------------------------------------------------
    def test_01_sequence_name(self):
        req = self._make_request()
        self.assertTrue(req.name.startswith('CAR/'), "Request should get a sequence name.")

    def test_02_candidate_matching_skill_and_role(self):
        req = self._make_request(role_id=self.role_sound.id)
        cands = req._match_candidate_employees()
        self.assertIn(self.emp_adv, cands)      # Sound Advanced >= Intermediate
        self.assertIn(self.emp_int, cands)      # Sound Intermediate >= Intermediate
        self.assertNotIn(self.emp_light, cands)  # no Sound skill

    def test_03_min_level_excludes_below(self):
        req = self._make_request()
        req.skill_requirement_ids.min_skill_level_id = self.lvl_adv  # require Advanced
        cands = req._match_candidate_employees()
        self.assertIn(self.emp_adv, cands)
        self.assertNotIn(self.emp_int, cands)  # Intermediate < Advanced

    def test_04_invite_waves_and_exclusion(self):
        req = self._make_request(role_id=self.role_sound.id)
        req.action_open()
        wiz = self._wizard(req)
        self.assertEqual(len(wiz.line_ids), 2)
        wiz.line_ids.filtered(lambda l: l.employee_id == self.emp_adv).selected = True
        wiz.action_invite_selected()
        self.assertEqual(len(req.invitation_ids), 1)
        self.assertEqual(req.invitation_ids.wave, 1)
        # wave 2: previously invited excluded
        wiz2 = self._wizard(req)
        self.assertEqual(len(wiz2.line_ids), 1)
        self.assertEqual(wiz2.line_ids.employee_id, self.emp_int)
        wiz2.line_ids.selected = True
        wiz2.action_invite_selected()
        self.assertEqual(len(req.invitation_ids), 2)
        self.assertEqual(max(req.invitation_ids.mapped('wave')), 2)

    def test_05_no_duplicate_invitation(self):
        from psycopg2 import IntegrityError
        from odoo.tools import mute_logger
        req = self._make_request()
        self.env['crew.availability.invitation'].create({
            'request_id': req.id, 'employee_id': self.emp_adv.id})
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.env['crew.availability.invitation'].create({
                    'request_id': req.id, 'employee_id': self.emp_adv.id})
                self.env.flush_all()

    def test_06_reminder_no_new_invitation(self):
        req = self._make_request()
        inv = self.env['crew.availability.invitation'].create({
            'request_id': req.id, 'employee_id': self.emp_adv.id})
        inv.action_remind()
        self.assertEqual(inv.reminder_count, 1)
        self.assertEqual(inv.state, 'reminded')
        self.assertEqual(len(req.invitation_ids), 1)

    def test_07_response_available_feeds_engine(self):
        req = self._make_request()
        inv = self.env['crew.availability.invitation'].create({
            'request_id': req.id, 'employee_id': self.emp_adv.id})
        inv.action_set_available()
        self.assertEqual(inv.response, 'available')
        # explicit crew -> a window/hole must now exist for the period
        win = self.env['crew.availability'].search([
            ('resource_id', '=', self.emp_adv.resource_id.id),
            ('date_start', '<', self.d2), ('date_end', '>', self.d1)])
        self.assertTrue(win, "Available response must register availability via the engine.")

    def test_08_response_standard_crew_no_engine(self):
        req = self._make_request()
        inv = self.env['crew.availability.invitation'].create({
            'request_id': req.id, 'employee_id': self.emp_int.id})  # standard mode
        inv.action_set_available()
        self.assertEqual(inv.response, 'available')
        self.assertFalse(self.env['crew.availability'].search([
            ('resource_id', '=', self.emp_int.resource_id.id)]),
            "Standard-schedule crew must not get engine windows.")

    def test_09_coverage_vs_staffing(self):
        req = self._make_request(headcount_needed=2)
        for emp in (self.emp_adv, self.emp_int):
            self.env['crew.availability.invitation'].create({
                'request_id': req.id, 'employee_id': emp.id}).action_set_available()
        self.assertEqual(req.available_count, 2)
        self.assertEqual(req.availability_coverage, 'sufficient')
        # staffing is separate: no slots yet
        self.assertEqual(req.planned_headcount, 0)
        self.assertEqual(req.staffing_display, '0 / 2')
        # add a planning slot linked to the request -> staffing rises, coverage unchanged
        self.env['planning.slot'].create({
            'resource_id': self.emp_adv.resource_id.id,
            'crew_request_id': req.id,
            'start_datetime': self.d1, 'end_datetime': self.d2})
        req.invalidate_recordset(['planned_headcount', 'staffing_display'])
        self.assertEqual(req.planned_headcount, 1)
        self.assertEqual(req.availability_coverage, 'sufficient')

    def test_10_exclude_already_answered(self):
        # a candidate who already declared availability for the period is not re-asked
        self.env['crew.availability.log'].create({
            'employee_id': self.emp_adv.id,
            'resource_id': self.emp_adv.resource_id.id,
            'date_start': self.d1, 'date_end': self.d2,
            'declared_state': 'available', 'origin': 'planner',
        })
        req = self._make_request()
        cands = req._match_candidate_employees(exclude_answered=True)
        self.assertNotIn(self.emp_adv, cands)
        cands_all = req._match_candidate_employees(exclude_answered=False)
        self.assertIn(self.emp_adv, cands_all)
