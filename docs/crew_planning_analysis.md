# Crew Availability, Planning & Work Declaration — Functional & Technical Analysis
*Pre-implementation analysis (NO code yet) — Backend (HR/Resource/Project/Planning/Timesheet) + Portal + WhatsApp*

| | |
|---|---|
| **Project** | Orentoo — Odoo 19.0 (Odoo.sh) |
| **Scope** | Generic Crew Planning extension (availability, invitations, work declaration) |
| **Core principle** | Customise the workflow **around** Odoo; standard objects stay the operational source of truth |
| **Status** | Analysis only — awaiting review before any development |
| **Date** | 2026-09-07 |

> Terminology is neutral (**Crew Member / Crew / Crew Portal / Availability Request**), never
> "freelancer". Every crew member is an `hr.employee`; a crew member may have **only portal
> access or none**.

---

# A. Current-state assessment

**This database is a rental-only install.** The foundation for this feature is **not
installed** — only `resource`, `portal`, `portal_rating` are present. Everything needed is
**available to install** (verified in `ir_module_module`): `hr`, `hr_holidays`, `hr_skills`,
`project`, `project_enterprise`, `project_forecast`, `planning`, `sale_planning`,
`sale_project`, `sale_project_forecast`, `hr_timesheet`, `sale_timesheet`, `whatsapp`.

**Custom code touches none of this domain** — a grep across `/home/odoo/src/user` for
`planning.slot|project.task|hr.employee|account.analytic.line|hr.skill` returns nothing. There
is **no collision** with existing Orentoo modules (rental_set, sale_flow, rental_purchase, …);
crew planning is a clean additive vertical. The only shared touch-points are `sale.order.line`
(already extended by rental) and `resource` (installed) — both additive.

**What standard already gives us (large):**

| Capability | Standard mechanism (file evidence) | Verdict |
|---|---|---|
| Effective availability | `resource.calendar._work_intervals_batch` = attendance − leaves; batched, tz-aware (`resource/models/resource_calendar.py:556`) | Reuse as source of truth |
| Per-person unavailability | `resource.calendar.leaves` with `resource_id` set, else company-global (`resource_calendar_leaves.py:47`; filter at `resource_calendar.py:529-552`) | Reuse |
| Skills + ordered levels | `hr.employee.skill.level_progress` 0–100 (`hr_skills/.../hr_employee_skill.py:54`); clean `>=` domains, AND-composable | Reuse |
| Planning shift = task | `planning.slot.task_id` (`sale_project_forecast/models/planning_slot.py`), `project_id` (`project_forecast`), `sale_line_id` (`sale_planning`) | Reuse — `task_id` already exists |
| Task → SOL → billing | `task.sale_line_id` (`sale_project/.../project_task.py:26`) → `account.analytic.line._timesheet_determine_sale_line()` (`sale_timesheet/.../hr_timesheet.py:117`) → `so_line` → `qty_delivered` | Reuse — no custom billing |
| SO → Project/Task | `product.service_tracking` + `_timesheet_service_generation()` on SO confirm (`sale_project/.../sale_order_line.py`) | Reuse |
| Publish/notify shift | `planning.slot.action_send`/`_send_slot` (`planning/.../planning_slot.py:1683,2343`); portal token; **no accept step** (scheduling = confirmation) | Reuse — matches §12 |
| WhatsApp | `whatsapp.template` on any model with a phone field + `mail.thread`; `whatsapp.composer` programmatic send | Reuse |
| Portal | `portal.mixin` (access_url/token), `CustomerPortal`, `ir.rule` per-partner, `portal.wizard` to grant access | Reuse |

# B. Gap analysis (per requirement)

| Req | Requirement | Classification |
|---|---|---|
| §2 | Standard = source of truth | Standard (constraint) |
| §3 | Unavailable-by-default + positive availability | Small extension — service mapping declarations to `resource.calendar.leaves` (see D) |
| §4A/B/C | Request from Project / Task / Period | Custom (request model) + prefill from standard |
| §4D | Crew self-service availability | Custom portal page → same leaves engine |
| §4E | Planner enters availability | Small extension — button on employee → leaves service |
| §5 | Audit log of availability changes | Custom (lightweight log model) |
| §6 | Don't re-ask known periods; available/partial/declined | Custom (log drives targeting; engine stays authoritative) |
| §7 | Validity rules + "can no longer work" | Small extension + custom workflow (replace portal self-unassign) |
| §8 | Candidate selection by skill/level/role | Standard + config (skills domains) wrapped in a wizard |
| §9 | Invitation waves | Custom (invitation model + wave tracking) |
| §10 | Request overview + KPIs | Custom (views on request/invitation) |
| §11 | Email + WhatsApp invitations, reminders | Standard (mail + whatsapp) + custom orchestration |
| §12 | Assignment = `planning.slot`; scheduling = confirmation | Standard planning; small notification wording tweak |
| §13–15 | Project→Task→Slot→Timesheet→SOL | Standard (reuse whole chain) |
| §16 | Work Declaration layer → Timesheet | Custom (thin model) + standard timesheet write |
| §17 | Crew Portal | Custom controllers/pages reusing standard data |
| §18 | Portal security | Standard (`ir.rule` + controllers + tokens) |

**Net:** ~70% standard/config; the custom part is the *workflow shell* (requests, invitations,
availability log, work declaration, portal) — the "customise around Odoo, not the engines"
principle.

# C. Proposed architecture

**Reused (unchanged):** `resource.calendar`, `resource.calendar.leaves`, `resource.resource`,
`hr.employee`, `hr.employee.skill`/`hr.skill.level`, `planning.slot` (+ `task_id`/`project_id`/
`sale_line_id`), `project.task`/`project.project`, `account.analytic.line`, `sale.order.line`,
`whatsapp.template`/`composer`, `portal.mixin`.

**Extended (thin `_inherit`):**
- `hr.employee` — crew flags (`is_crew`, crew type), "enter availability" action (portal
  `employee_token` already exists).
- `planning.slot` — "report I can't work" action + link to work declarations; **task_id reused,
  not added.**
- `resource.resource` — helper delegating to the leaves service.
- `sale.order.line` / `project.task` — only if needed for prefill (likely nothing).

**New custom models:** `crew.availability.request`, `crew.availability.invitation`,
`crew.availability` (log/declaration), `crew.work.declaration`.

**Wizards:** candidate-selection/invite; "enter availability on behalf"; "report can't work".

**Controllers / portal pages (`crew_portal`):** `/my/availability`, `/my/planning`,
`/my/hours`, `/my/profile` (phased) — crew-namespaced to avoid the existing `/my/timesheets`
and `/my/tasks` routes.

**Scheduled actions:** invitation reminder cron; optional close-expired-requests; optional
nightly log ↔ leaves consistency check.

# D. Availability technical design (single source of truth)

**Chosen mechanism (the only viable standard one):** a **broad shared "Crew" `resource.calendar`**
(generous / 24×7 attendance) + **per-resource `resource.calendar.leaves`** for everything
else. Positive availability = **absence** of a leave inside the broad attendance.

Alternatives, all investigated and rejected:
- *No calendar* → "fully flexible" → **always available** (wrong default).
- *Empty-attendance calendar* → never available, but leaves only **subtract** and attendances
  are **weekly-recurring** — **no native way to add a single-date availability.** Dead end.
- *`time_type='other'` leaves* do not **add** availability where no attendance exists. Dead end.
- Therefore **broad attendance + carve leaves** is the only standard route;
  `_leave_intervals_batch` already filters by `resource_id` and merges overlaps.

**Semantics:**
- **Unknown / not-yet-confirmed** = a standing "blanket" leave → engine sees *unavailable*, so
  standard **Auto-Plan will not schedule** an unconfirmed crew member (critical for §2/§12).
- **Available** = split/remove the leave to expose the window (a hole).
- **Definitely unavailable** = a leave that persists, tagged with a *declined* reason.

The engine cannot distinguish *unknown* vs *declined* (both are "leave"). That distinction lives
in the **`crew.availability` log**, which drives §6 "don't re-ask" — **not** the engine. Effective
availability stays 100% standard; the log is advisory/audit only.

**One idempotent service** `_apply_availability(resource, start, end, state, origin, refs)` owns
all leave create/split/merge, so overlaps (§6) are handled in one place:
- store **UTC**, compute in **resource.tz** (resource tz overrides calendar tz);
- **DST**: `pytz.localize` fold/gap is the main sharp edge (standard raises on ambiguous times)
  — documented and tested;
- overlaps normalised to non-overlapping intervals before writing (interval algebra like
  `odoo.tools.intervals`).

Planning `auto_plan_ids()`, `allocated_hours` and conflict detection all read
`_work_intervals_batch`, so they respect these leaves automatically — **no parallel engine.**
*Caveat:* a 24×7 base calendar makes `allocated_percentage` meaningless for utilisation
reporting — acceptable for event crew (flagged).

# E. Data model (custom)

**`crew.availability.request`** — `name`, `request_type` (task/project/period), `project_id`,
`task_id`, `date_start`, `date_end`, `role_id`, `skill_requirement_ids`, `headcount_needed`,
`state`, `company_id`; KPI computes (invited / available / partial / unavailable / pending).

**`crew.availability.invitation`** — `request_id`, `employee_id`, `wave` (int), `channel`
(email/whatsapp/both), `state` (selected/sent/reminded/responded/expired), `sent_on`,
`last_reminder_on`, `response` (available/partial/unavailable/pending), `response_start`/
`response_end` (partial), `mail_message_ids`. Uniqueness `(request_id, employee_id)` blocks
duplicate invitations across waves.

**`crew.availability`** (log/declaration) — `employee_id`/`resource_id`, `date_start`,
`date_end`, `state` (available/unavailable), `origin` (self_portal/task_request/project_request/
period_request/planner), `request_id`, `project_id`, `task_id`, `changed_by`, `create_date`,
`previous_state`, `new_state`, `leave_ids`. Append-only for audit; "current" view derived.

**`crew.work.declaration`** — `slot_id` (unique), `employee_id`/`project_id`/`task_id`/
`sale_line_id` (related from slot), `planned_start/end/duration` (from slot), `actual_start`,
`actual_end`, `break_minutes`, `worked_hours` (computed), `comment`, `state`
(draft/submitted/approved/rejected), `timesheet_id` (the created `account.analytic.line`, for
idempotency).

**Skill requirement line** (embedded) — `skill_id`, `min_skill_level_id` (compared via
`level_progress >=`).

# F. State machines

- **Availability Request:** `draft → open → (partially_fulfilled) → fulfilled → closed`
  (+ `cancelled`). Fulfilled when confirmed-available ≥ headcount.
- **Invitation:** `selected → sent → reminded* → responded → expired`. Reminder is a transition
  on an *existing* invitation, never a new record (§9/§11).
- **Availability Response:** `pending → available | partial | unavailable`.
- **Work Declaration:** `draft → submitted → approved (→ timesheet written)`; `→ rejected →
  draft`. Approval is idempotent: create the timesheet if `timesheet_id` empty, else update it.

# G. End-to-end workflows

1. **Task-based invitation:** Task → "Request Availability" (prefills project/task/start/end/SOL)
   → candidate wizard (skills/role) → select wave-1 → Invite (email/WA: *"availability only, not
   scheduled"*) → responses become `crew.availability` (holes in leaves) → planner schedules →
   `planning.slot` (task_id set) → publish notifies (*"you're scheduled…"*).
2. **Project-based:** identical, prefilled from project period; task chosen later on the slot.
3. **General period:** request with no project/task; pure availability harvesting.
4. **Self-service:** crew opens `/my/availability`, marks available/unavailable → same service →
   log `origin=self_portal`.
5. **Planner-entered:** button on employee/resource → same service → `origin=planner`.
6. **Multi-wave:** wave-1 of 10 invited; reopen wizard → previously-invited **excluded** →
   wave-2; reminders don't duplicate.
7. **Planning notification:** standard `action_send`; reword template to "scheduled, tell us ASAP
   if you can't"; **no** second confirmation.
8. **Work Declaration → Timesheet → SOL:** slot → crew confirms/edits actuals in `/my/hours` →
   submit → planner approves → write `account.analytic.line(task_id, unit_amount, employee_id)`
   → standard `_timesheet_determine_sale_line()` sets `so_line` from `task.sale_line_id` →
   `qty_delivered` on the correct SOL for billing. **No manual project/task/SOL reselection.**

# H. Risks & edge cases

- **Overlapping/partial availability** — resolved to non-overlapping intervals in the single
  leaves service; partial responses punch a hole only for the offered sub-window.
- **DST/timezones** — store UTC, compute in resource tz; `pytz` fold/gap is the main sharp edge.
- **Changed task/slot dates** — written leaves stay; slot changes raise standard
  `publication_warning`; the request keeps its own window (no retro-rewrite of the log).
- **"Can no longer work" after planning** — must **not** use standard portal self-unassign (it
  silently blanks `resource_id`). Custom action keeps the slot, flags it, notifies the planner
  (§7/§12).
- **Cancellation after planning** — never auto-cancel a published slot on availability withdrawal.
- **Inactive employee** — archive resource → auto-excluded from `_work_intervals_batch` and
  candidate search.
- **Duplicate email/WhatsApp** — `(request, employee)` uniqueness + wave/reminder counters; WA
  needs an **approved** template + `whatsapp.account`.
- **Duplicate timesheets** — one WD per slot + `timesheet_id` back-reference → approval is
  create-or-update.
- **SOL/task change after hours submitted** — standard recomputes `so_line` unless edited; lock
  `so_line`/hours on **approved** declarations to avoid silent re-billing.
- **Performance (thousands of crew)** — leaves batched/indexed; candidate search is a skills
  domain; blanket-leave punching is O(windows), not O(crew²).

# I. Recommended module structure

- **`crew_planning`** (backend core): availability leaves service, requests, invitations,
  candidate wizard, work declaration, `planning.slot` glue, WhatsApp orchestration, KPIs.
  *Depends:* `planning`, `sale_project_forecast`, `sale_timesheet`, `hr_skills`, `hr_timesheet`,
  `whatsapp`, `resource`.
- **`crew_portal`** (portal): controllers, pages, portal `ir.rule`/security, "report can't work".
  *Depends:* `crew_planning`, `portal`.
- **`orentoo_crew`** (optional, thin): org-specific config, calendar seeding, wording, data —
  keeps `crew_planning`/`crew_portal` generic and reusable.

*(Names provisional. The heavy standard dependency tree is unavoidable given the greenfield DB —
a deliberate "reuse standard" cost, not custom weight.)*

# J. Implementation phases

- **Phase 0 — Foundation:** install/configure the standard stack (hr, project, planning,
  sale_project_forecast, sale_timesheet, hr_skills, hr_timesheet, whatsapp, portal); seed the
  shared Crew calendar; confirm `planning.slot.task_id`/billing chain live.
- **Phase 1 — Availability engine:** leaves service + audit log + backend "enter availability"
  (§4E) + unit tests (overlap/DST).
- **Phase 2 — Requests & invitations:** request models (task/project/period), candidate wizard
  (skills), waves, **email** invitations, overview + KPIs.
- **Phase 3 — WhatsApp** channel + reminders.
- **Phase 4 — Crew Portal:** My Availability, My Planning (+ "can't work"), security rules.
- **Phase 5 — Work Declaration → Timesheet:** WD model, approval → timesheet (idempotent),
  My Hours.
- **Phase 6 — Validity rules & polish:** future-window limits, cut-off hours, dashboards, WA
  template approval.

---

## Open decisions before Phase 0

1. **Footprint:** greenfield DB means installing the **full enterprise Project / Planning /
   Timesheet / HR / WhatsApp stack** on a today rental-only system — proceed on this dev branch,
   or validate on a separate branch/build first?
2. **Availability model:** bias to the recommended **24×7 blanket-leave** design, or spike a
   per-crew-calendar variant for comparison before committing?
3. **Module naming/split:** confirm `crew_planning` + `crew_portal` (+ optional `orentoo_crew`).
