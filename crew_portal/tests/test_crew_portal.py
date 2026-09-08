# -*- coding: utf-8 -*-
import re

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'crew_portal')
class TestCrewPortal(HttpCase):

    def setUp(self):
        super().setUp()
        self.user = self.env['res.users'].create({
            'name': 'Crew Portal User',
            'login': 'crewportal',
            'password': 'crewportal',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        self.emp = self.env['hr.employee'].create({
            'name': 'Portal Crew',
            'is_crew': True,
            'crew_availability_mode': 'explicit',
            'user_id': self.user.id,
        })

    def test_portal_availability_and_planning(self):
        self.authenticate('crewportal', 'crewportal')

        # My Availability renders
        res = self.url_open('/my/availability')
        self.assertEqual(res.status_code, 200)
        self.assertIn('My Availability', res.text)

        # Register availability via the portal form (with CSRF)
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', res.text)
        self.assertTrue(m, "CSRF token must be present on the page")
        res2 = self.url_open('/my/availability/register', data={
            'csrf_token': m.group(1),
            'date_start': '2027-01-10T08:00',
            'date_end': '2027-01-10T18:00',
            'state': 'available',
        })
        self.assertEqual(res2.status_code, 200)
        window = self.env['crew.availability'].search([('employee_id', '=', self.emp.id)])
        self.assertTrue(window, "Portal registration must create an availability window")

        # My Planning renders
        res3 = self.url_open('/my/planning')
        self.assertEqual(res3.status_code, 200)
        self.assertIn('My Planning', res3.text)
