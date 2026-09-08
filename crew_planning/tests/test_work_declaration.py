# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'crew_planning')
class TestWorkDeclaration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.now = cls.env['crew.availability.engine']._now()
        cls.emp = cls.env['hr.employee'].create({'name': 'Wanda Worker', 'is_crew': True})
        cls.project = cls.env['project.project'].create({
            'name': 'Crew Project', 'allow_timesheets': True})
        cls.task = cls.env['project.task'].create({
            'name': 'Stage Build', 'project_id': cls.project.id})
        cls.start = cls.now - timedelta(hours=10)
        cls.end = cls.now - timedelta(hours=2)  # an 8h shift that already ended

    def _make_slot(self):
        return self.env['planning.slot'].create({
            'resource_id': self.emp.resource_id.id,
            'project_id': self.project.id,
            'task_id': self.task.id,
            'start_datetime': self.start,
            'end_datetime': self.end,
        })

    def _declared(self, slot, break_min=0):
        wd = slot._get_or_create_work_declaration()
        wd.write({'actual_start': self.start, 'actual_end': self.end,
                  'break_minutes': break_min})
        return wd

    def test_01_worked_hours_minus_break(self):
        wd = self._declared(self._make_slot(), break_min=30)
        self.assertAlmostEqual(wd.worked_hours, 7.5, places=2)

    def test_02_submit_approve_creates_timesheet_once(self):
        slot = self._make_slot()
        wd = self._declared(slot)
        wd.action_submit()
        self.assertEqual(wd.state, 'submitted')
        wd.action_approve()
        self.assertEqual(wd.state, 'approved')
        self.assertTrue(wd.locked)
        self.assertTrue(wd.timesheet_id)
        self.assertAlmostEqual(wd.timesheet_id.unit_amount, 8.0, places=2)
        self.assertEqual(wd.timesheet_id.task_id, self.task)
        self.assertEqual(wd.timesheet_id.employee_id, self.emp)
        ts = wd.timesheet_id
        # Idempotent: re-ensuring does not create a second timesheet.
        wd._ensure_timesheet()
        self.assertEqual(wd.timesheet_id, ts)

    def test_03_locked_declaration_is_immutable(self):
        wd = self._declared(self._make_slot())
        wd.action_submit()
        wd.action_approve()
        with self.assertRaises(UserError):
            wd.comment = 'too late'

    def test_04_reopen_removes_timesheet_and_allows_recycle(self):
        slot = self._make_slot()
        wd = self._declared(slot)
        wd.action_submit()
        wd.action_approve()
        ts = wd.timesheet_id
        self.assertFalse(wd.timesheet_financially_locked)
        wd.action_reopen()
        self.assertEqual(wd.state, 'reopened')
        self.assertFalse(wd.locked)
        self.assertFalse(wd.timesheet_id)
        self.assertFalse(ts.exists(), "The draft timesheet must be removed on reopen.")
        # a corrected declaration re-approves cleanly into a fresh timesheet
        wd.break_minutes = 60
        wd.action_submit()
        wd.action_approve()
        self.assertTrue(wd.timesheet_id)
        self.assertAlmostEqual(wd.timesheet_id.unit_amount, 7.0, places=2)

    def test_05_one_declaration_per_slot(self):
        slot = self._make_slot()
        slot._get_or_create_work_declaration()
        with self.assertRaises(Exception):
            self.env['crew.work.declaration'].create({'slot_id': slot.id})
            self.env.flush_all()

    def test_06_cannot_submit_without_actuals(self):
        slot = self._make_slot()
        wd = slot._get_or_create_work_declaration()
        wd.write({'actual_start': False, 'actual_end': False})
        with self.assertRaises(UserError):
            wd.action_submit()

    def test_07_end_before_start_rejected(self):
        slot = self._make_slot()
        wd = slot._get_or_create_work_declaration()
        with self.assertRaises(ValidationError):
            wd.write({'actual_start': self.end, 'actual_end': self.start})

    def test_09_schedule_shift_from_task_prefills_and_links(self):
        self.task.write({'planned_date_begin': self.start,
                         'date_deadline': self.end})
        action = self.task.action_crew_schedule_shift()
        ctx = action['context']
        self.assertEqual(ctx['default_task_id'], self.task.id)
        self.assertEqual(ctx['default_project_id'], self.project.id)
        self.assertEqual(ctx['default_start_datetime'], self.start)
        self.assertEqual(ctx['default_end_datetime'], self.end)
        # a slot created from that context is linked back to the task
        slot = self.env['planning.slot'].with_context(**ctx).create({
            'resource_id': self.emp.resource_id.id})
        self.assertEqual(slot.task_id, self.task)
        self.assertEqual(slot.project_id, self.project)
        self.assertIn(slot, self.task.planning_slot_ids)
        self.task.invalidate_recordset(['planning_slot_count'])
        self.assertEqual(self.task.planning_slot_count, 1)

    def test_10_rejected_declaration_can_be_resubmitted(self):
        slot = self._make_slot()
        wd = self._declared(slot)
        wd.action_submit()
        wd.action_reject()
        self.assertEqual(wd.state, 'rejected')
        # the crew fixes it and resubmits -> allowed (reject means "redo")
        wd.break_minutes = 15
        wd.action_submit()
        self.assertEqual(wd.state, 'submitted')

    def test_08_approve_requires_project(self):
        slot = self.env['planning.slot'].create({
            'resource_id': self.emp.resource_id.id,
            'start_datetime': self.start, 'end_datetime': self.end})
        wd = slot._get_or_create_work_declaration()
        wd.write({'actual_start': self.start, 'actual_end': self.end})
        wd.action_submit()
        with self.assertRaises(UserError):
            wd.action_approve()
