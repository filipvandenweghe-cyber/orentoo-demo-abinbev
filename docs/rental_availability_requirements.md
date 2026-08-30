# Rental Availability — Repairs, Sets & Warehouse Breakdown
*Functional & Technical Requirements, Goals & Tests — Backend / Sales (Rental) + Inventory (v2, for approval)*

| | |
|---|---|
| **Project** | Orentoo — Odoo 19.0 (Odoo.sh) |
| **Where it lives** | Folded into **rental_set** (no new module) |
| **Hard deps** | sale_stock_renting, sale_renting, sale_stock, stock (already in rental_set) |
| **Optional dep** | **repair** — used only if installed; must not crash or show when absent |
| **Channel** | Rental order line availability + its pop-up; set availability |
| **Author** | Pro-Designed.com |
| **Status** | Requirements v2 — for approval; no code yet |
| **Date** | 2026-08-30 |

# 0. Changes vs v1 (from review)
1. **Repair is optional.** If the `repair` module is not installed: no repair deduction,
   no repair line in the pop-up, **no crash** (soft model check).
2. **"At Customer" is a location** (the company rental location). The pop-up breakdown
   is therefore **location-driven**, which simplifies it.
3. **Repairs must be woven into the availability figure.** So we *do* extend the
   availability computation (a targeted override), not just the display. The "keep
   native, don't rewrite" decision applies **only** to the multi-step over-count, not to
   repairs.
4. **Own-demand / no-double-count is a first-class requirement to verify** (see §3.3):
   the current code adds back own demand for confirmed orders but then caps at
   `qty_available`, which may negate the add-back. This must be verified and tested.
5. **Tests reassessed** (see §7) to match: folding into rental_set, optional repair,
   own-demand correctness, and location-based breakdown.
6. **Decisions:** multi-step over-count → **keep native + show portion in pop-up (1B)**;
   placement → **fold into rental_set**.

# 1. Purpose & Business Context
Rental staff need a **trustworthy "available for this period" figure** and a way to
**see where the stock actually is**. Two gaps cause wrong numbers and confusion:
1. **Repairs are invisible to availability.** A broken unit in an open repair order is
   physically present but **not rentable** — yet standard availability still counts it.
2. **The figure is a single opaque number.** Staff cannot see that (e.g.) of 10 units, 3
   are at a customer, 2 are in QC (not put away), 1 is in repair — so only 4 are pickable.

Separately, **set availability** (rental_set) uses custom own-demand/competing-demand
math that is fragile. It should be the **limiting component's whole-set count**, built on
the same (now repair-aware) component availability, with own-demand handled correctly.

# 2. Background & Root-Cause (verified in code)
- **Native rental availability** (`sale_stock_renting.sale.order.line._compute_qty_at_date`):
  for start ≤ now uses `qty_available(from_date,to_date,warehouse_id)`; for a future
  start uses `virtual_available`. Other rentals are subtracted via
  `_get_unavailable_qty(..., ignored_soline_id=line.id, warehouse_id=...)`, which
  excludes **this line's** rental demand.
- **rental_set already overrides this** with a custom forecast
  (`_compute_forecast_availability`) that walks stock moves over the period and, for
  confirmed orders, **adds back own outgoing demand** — then **caps at
  `qty_available`** (`current_stock_original`). Because `qty_available` is already
  reduced by the order's own reservation, **the cap can cancel the add-back** for
  current-start orders → confirmed orders may under-count their own availability.
  **This is the double-count logic to verify (§3.3).**
- **Warehouse scoping:** with `warehouse_id` context, `qty_available`/`virtual_available`
  cover the warehouse **view location** = **Input + Quality Control + Stock**. QC/Input
  stock is not yet rentable → the raw figure can **over-count** during multi-step
  reception.
- **Repairs:** `repair.order.move_id` is created **only in `action_repair_done`**. While
  `confirmed`/`under_repair` there is **no stock move**, so the forecast never deducts
  it. Usable fields: `product_id`, `lot_id`, `product_qty`, `state`, `create_date`,
  `schedule_date`, `location_id`.
- **Rental "At Customer"** is an internal location (company rental location,
  `company.rental_loc_id`) — so it is naturally part of a location breakdown.

# 3. Design Decisions — Options, Pros/Cons & Rationale
## 3.1 Multi-step over-count (QC/Input not rentable)
**Decision:** **keep native availability** (do not re-implement the forecast engine) and
make the reality **visible** via the per-location breakdown in the pop-up; rely on
**standard padding/preparation time** (config only, no custom padding code) as the
reception buffer.

## 3.2 Repairs → availability, and optional dependency
- **Extend the availability computation** (targeted override of the rental_set forecast):
  after the normal figure, **subtract** the quantity tied up in **open** repairs
  (`state not in ('done','cancel')`) whose window `[create_date → schedule_date,
  extended to now if overdue]` overlaps the rental period. Keyed by product (and `lot_id`
  for serials). The unit stays at its location; this is a logical deduction.
- **Optional `repair`:** guard every repair access with a model-presence check
  (`'repair.order' in self.env`). If absent: **no deduction, no pop-up repair line, no
  crash**. `repair` is **not** added to rental_set's hard `depends`.

## 3.3 Own-demand for confirmed orders (no double-count) — VERIFY
The requirement **still holds**: a confirmed order must see its **own** reserved units as
available **to itself** (not subtracted twice). Native `ignored_soline_id` removes the
*rental-demand* layer, but the *physical* `qty_available` is still reduced by the order's
own reservation — so an add-back (or an equivalent base that ignores own reservation) is
needed for the current-start branch.
**Decision:** keep an explicit own-demand correction, but **fix the cap** so the add-back
is not negated (cap at *total rentable ignoring own reservation*, not at the
already-reduced `qty_available`). Cover with a dedicated test (T-05). Do **not** assume
`ignored_soline_id` alone is sufficient for confirmed current-start orders.

## 3.4 Set availability
**Decision:** set availability = `min over leaf components of
floor( component_availability / cumulative_qty_per_set )`, where `component_availability`
is the same repair-aware, own-demand-correct figure used for standalone lines. Remove the
separate manual competing-demand arithmetic where the component figure already accounts
for it. Non-storable components remain limitless; nested sets traverse to leaves.

## 3.5 Placement
**Decision:** **fold into rental_set** (no separate module). Availability, sets and the
pop-up already live there; one module keeps the logic coherent and avoids cross-module
override ordering.

## 3.6 Pop-up breakdown = location-driven
**Decision:** build the breakdown from **internal locations** for the warehouse + period:
- per-location on-hand (Input / Quality Control / Stock …),
- **At Customer** = the rental location's on-hand (rented out),
- **In Repair** = open-repair qty (only if `repair` installed; shown as its own line
  because the unit still sits in a physical location and would otherwise be hidden),
- **Pickable** = usable-stock on-hand − in-repair (the net staff can ship now).

# 4. Goals
- **G1** Availability excludes units in open repair over the repair window — **only when
  `repair` is installed**, and never crashes when it isn't.
- **G2** The pop-up shows a location-driven breakdown (incl. At Customer and, if present,
  In Repair) and the net **Pickable** figure.
- **G3** Set availability is the limiting component's whole-set count, built on the same
  component availability.
- **G4** No custom padding logic — standard preparation/padding config only.
- **G5** **No double-count:** a confirmed order sees its own reserved units as available
  to itself (verified, not assumed).
- **G6** Small, isolated footprint inside rental_set; native forecast engine not rewritten.

# 5. Functional Requirements
## 5.1 Repair-aware availability (RAV-01…04)
- **RAV-01** Availability is reduced by product qty tied up in **open** repairs
  (`state not in ('done','cancel')`) whose window overlaps the rental period.
- **RAV-02** Serial products: a repair on a `lot_id` removes that one unit; qty products:
  remove `product_qty`.
- **RAV-03** `done`/`cancel` repairs do not reduce availability.
- **RAV-04** If `repair` is not installed: no deduction, no repair UI, **no error**.

## 5.2 Availability pop-up breakdown (RAV-05…07)
- **RAV-05** Show, for the picking warehouse + period: per-internal-location on-hand
  (Input / QC / Stock …), **At Customer**, **In Repair** (if repair installed), and net
  **Pickable**.
- **RAV-06** Repairs get an explicit line (only when repair installed).
- **RAV-07** Read-only; adds no blocking behaviour.

## 5.3 Set availability (RAV-08…09)
- **RAV-08** Set availability = `min over leaf components of
  floor( component_availability / cumulative_qty_per_set )`.
- **RAV-09** Non-storable components are limitless; nested sets traverse to leaves; own
  demand handled per §3.3.

## 5.4 Own-demand & guards (RAV-10…12)
- **RAV-10** A confirmed order's own reserved units count as available to itself
  (no double-count; the cap must not negate the add-back).
- **RAV-11** Padding/preparation time is standard config; this work adds none.
- **RAV-12** Only rental orders (`is_rental_order`) and storable products are affected.

# 6. Technical Approach (proposed)
- **Optional repair helper:** on `product.product`, a method returning open-repair qty
  overlapping `[from_date, to_date]` for a warehouse (and optional lot), implemented as
  `if 'repair.order' not in self.env: return 0.0` then a search on open repairs. No
  import of the repair module; pure registry check.
- **Availability:** extend rental_set's `_compute_forecast_availability` /
  `_compute_qty_at_date` to (a) subtract the repair helper and (b) fix the own-demand cap
  (§3.3). Standalone and component lines share this figure.
- **Set availability:** `_compute_set_availability` reads the component figure and applies
  `floor(min(avail / qty_per_set))`.
- **Pop-up:** extend the native `qty_at_date_widget` (OWL) + server data with the
  location-driven breakdown; repair line rendered only when repair is installed.

# 7. Tests (reassessed — `rental_set/tests/test_rental_availability.py`)
| # | Test | Verifies | Requirement |
|---|---|---|---|
| T-01 | test_open_repair_reduces_availability | open repair over the period lowers availability by product_qty | RAV-01 |
| T-02 | test_done_repair_does_not_reduce | a `done` repair does not reduce availability | RAV-03 |
| T-03 | test_repair_outside_period_ignored | repair window not overlapping the period → no effect | RAV-01 |
| T-04 | test_serial_repair_removes_one_unit | repair on a serial removes exactly that unit | RAV-02 |
| T-05 | test_confirmed_own_demand_not_double_counted | confirmed order sees its own reserved units as available (add-back not negated by the cap) | RAV-10, G5 |
| T-06 | test_set_availability_limiting_component | set avail = floor(min component avail / qty-per-set) | RAV-08 |
| T-07 | test_set_non_storable_limitless | non-storable components don't constrain the set | RAV-09 |
| T-08 | test_breakdown_is_location_consistent | breakdown: Σ per-location on-hand and Pickable = usable on-hand − in-repair | RAV-05 |
| T-09 | test_repair_not_installed_no_crash | with repair absent (simulated), availability computes and no repair UI/deduction | RAV-04 |
| T-10 | test_non_rental_untouched | non-rental sale line availability unchanged | RAV-12 |
| T-11 | test_existing_set_availability_regression | prior rental_set set-availability tests still pass (no regression) | G3 |

*Note:* existing rental_set availability tests will be **re-run and adjusted** where the
figure legitimately changes (repair deduction, cap fix); any that encoded the old capped
behaviour will be updated to the corrected expectation, documented in the commit.

# 8. Out of Scope / Deferred
- Rewriting the native forecast to a usable-location min-over-period engine (kept native).
- Any change to native padding/preparation-time logic.
- Cleaning/QC as an explicit rentability gate beyond pop-up visibility (a return-route
  location step, tracked separately).
