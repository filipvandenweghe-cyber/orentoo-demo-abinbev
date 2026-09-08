# Crew Portal — Requirements (as built)

Module: **`crew_portal`**. Depends: `crew_planning`, `portal`. Odoo **19.0**.

Self-service for crew members (external or internal, without backend access).

> **Security invariant (R0):** every route resolves the logged-in user's
> employee (`_crew_employee`) and reads/writes **only that person's data**.
> `sudo` is used for controlled writes but is always scoped to the resolved
> employee; a non-crew user sees the "no crew profile" page.

---

## 1. Home cards
- **R1.1** Three crew cards appear on the portal home **only for crew members**
  (gated by an `is_crew` employee linked to the user): **My Availability**,
  **My Planning**, **My Hours**, each with a bundled icon and a live counter.
- **R1.2** Counters: availability windows count · upcoming shifts count ·
  shifts awaiting a declaration count.
- **R1.3** A planner can **hide standard portal cards** per crew member
  (sales/invoices/purchases/projects/tasks/timesheets/subscriptions/signatures).
  This is enforced by overriding the **`/my/counters`** route so the zeroing is
  the *last word* after every app's own counter contribution (the session
  `portal_counters` cache is refreshed too), reliably hiding those cards.

## 2. My Availability (`/my/availability`)
- **R2.1** Lists the crew member's registered availability windows (From / To /
  last updated) with a **Remove** action that recompiles the engine.
- **R2.2** **Register availability**: From / To / Available-or-Unavailable →
  fed into the Crew Availability Engine (`origin=self_portal`,
  entry-horizon enforced). On mobile/portrait these fields **stack vertically**;
  inline from tablet width up.
- **R2.3** **Open availability requests**: the crew member's pending invitations
  (future requests only, chronological) shown as cards with the request header,
  posted-at, **requested period** and indicative effort, plus **I'm available /
  Not available** actions. Each card makes clear this is *only a request for
  availability — not yet a booking*.

## 3. My Planning (`/my/planning`)
- **R3.1** Upcoming shifts assigned to the crew member (end ≥ now), showing
  start → end (no seconds), project, task and role.
- **R3.2** **"I can no longer work this shift"** with an optional reason →
  calls the backend action (policy-aware; see crew_planning R6.3). Once
  reported, the card shows a confirmation instead of the form.

## 4. My Hours (`/my/hours`)
- **R4.1** **Shifts to declare**: started shifts assigned to the crew member,
  excluding ones reported "cannot work". A shift is editable (shows the Submit
  form) only while its declaration is **draft / reopened / rejected**; the form
  prefills actual start/end from the plan and takes break minutes + a comment.
  Submitting creates/updates the declaration and submits it.
- **R4.2** The header of each to-declare card **stacks on portrait** (start →
  on line 1, end on line 2, project + description on line 3) and stays on one
  line from tablet width up.
- **R4.3** **Submitted / approved / rejected** shifts are shown **read-only**
  with their hours and status.
- **R4.4** The submit route is **guarded and idempotent**: it acts only on an
  editable, unlocked declaration; a stale or double POST on an already
  submitted/approved one is a silent no-op (never the website error page).

## 5. Localisation
- Datetimes are formatted with the month spelled out in the **user's timezone**
  (`format_datetime`); browser `datetime-local` inputs are parsed from/returned
  to the user's tz and stored as naive UTC.

## 6. Testing notes
Portal behaviour is primarily validated through the backing `crew_planning`
model/logic tests (counter-hiding map, declaration lifecycle and state gating,
self-unassign policy). The `/my/counters` override was additionally verified
against the live routing map (it resolves to `CrewPortal.counters`).
