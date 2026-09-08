# -*- coding: utf-8 -*-
"""Crew Planning — generic crew availability, invitations, scheduling and work
declaration for Odoo.

Design principle: customise the workflow AROUND Odoo and keep the standard
objects as the source of truth. Concretely:
- Availability lives in standard ``resource.calendar.leaves`` (engine-managed),
  never a parallel store; staffing reads only leaves.
- Scheduling uses standard ``planning.slot`` (extended with a Task link).
- Worked hours become standard timesheets (``account.analytic.line``) that flow
  to the Sales Order Item through the native chain.

See ``docs/crew_planning_requirements.md`` for the full, as-built requirements.
"""
from . import models
from . import wizard
