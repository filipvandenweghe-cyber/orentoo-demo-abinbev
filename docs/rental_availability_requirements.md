# Rental Availability — Repairs, Sets & Warehouse Breakdown
*Functional & Technical Requirements, Goals & Tests — Backend / Sales (Rental) + Inventory (v7, for approval)*

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
7. **Reservation split is shown explicitly (v3).** Rather than hide the own-demand
   correction inside add-back/cap math, the pop-up shows **Reserved by this order** and
   **Reserved by other orders** as their own lines. The availability number then becomes
   self-explanatory and auditable — you can *see* that this order's own reservation is
   counted as available to itself.
8. **"At Customer" line removed (v4).** A unit physically at a customer is a unit
   **committed to an order**, so it is already represented (period-correctly) inside
   **Reserved by other orders** (or this order). A separate "At Customer" line would
   double-count it — and, being period-blind, would wrongly reduce availability for a
   future rental that the unit returns in time for. The period-aware reserved/other-orders
   figure is the correct and sufficient representation.
9. **Native forecast already handles "returned early → available" (v5).** Verified in
   code: confirming a rental order registers **both** the pickup **and** the return
   transfer immediately. So a competing order that returns before our period holds
   nothing during it, and the full stock is available again — the native figure is
   correct, with **no forecast rewrite and no padding crutch needed** for this case.
   Consequently **Available for Rent = Total stock − Reserved(others) − In Repair**
   equals the native availability figure *exactly* (checked for both overlapping and
   future periods). There is therefore no "Option A vs B" — it is one number.
10. **Pop-up reordered to an accounting flow (v5).** `Total stock − Reserved by other
    orders − In Repair = Available for Rent`, then *of which reserved for this order*,
    then *Located in: Input / QC / Stock*. "Total stock" is computed as
    `Available + Reserved(others) + In Repair` so it is warehouse-scoped and always
    reconciles exactly with the figure shown.
11. **Location list = CURRENT on-hand per location, summing to Total (v6→v7).** To keep
    "Total stock" a stable anchor, the location list partitions Total across physical
    buckets: warehouse internal locations (Input/QC/Stock…), **At customer**, **In
    repair**, and a small reconciling **Other / in transit** bucket. It uses **current
    physical quants** (always ≥ 0) — deliberately **not** a per-location forecast to
    pickup. Rationale (v7): forecasting per location blindly applied pending internal
    staging/pick moves (Stock→Packing Zone) and partial reservations, producing a
    phantom "Packing Zone 8" and a negative "In transit −1" on a real order (S01532,
    only 7 units, both in Stock). Current on-hand is robust and honest; period-awareness
    stays in "Available for Rent". This is a *physical-presence* lens (a unit can sit at
    Stock yet be reserved by another order), distinct from the availability math; both
    anchor to the same Total.

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

## 3.3 Own-demand for confirmed orders (no double-count) — SHOW IT, don't hide it
The requirement **still holds**: a confirmed order must see its **own** reserved units as
available **to itself** (not subtracted twice). Today's code tries to solve this with a
hidden add-back that is then negated by a cap at `qty_available` — opaque and buggy.
**Decision (the agreed solution):** make the reservation split **explicit in the pop-up**
rather than hide a correction. The pop-up shows:
- **Reserved by this order** — quantity this order has already reserved (its own pickup
  moves), which **counts as available to this order**;
- **Reserved by other orders** — quantity reserved by *other* orders, which is **not**
  available to this order.
The headline availability number is then defined transparently and *verifiably* from
those lines, so the double-count question is answered by inspection. The underlying figure
still counts this order's own reservation as available to itself; the pop-up now proves it.
Covered by tests T-05 (number correct) and T-12 (both reservation lines shown).

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
**Decision:** build the breakdown from **warehouse internal locations** + the
period-aware reservation split (no separate "At Customer" line — see §0.8):
- per-location on-hand in the warehouse (Input / Quality Control / Stock …),
- **Reserved by this order** — period-overlapping commitment of *this* order (its
  reservations + not-yet-returned deliveries); **available to this order** (§3.3),
- **Reserved by other orders** — period-overlapping commitment of *other* orders
  (includes their units still out at customers); **not** available to this order (§3.3),
- **In Repair** = open-repair qty (only if `repair` installed; shown as its own line
  because the unit still sits in a physical location and would otherwise be hidden),
- **Pickable / Available to this order** = usable-stock on-hand − reserved-by-others −
  in-repair (+ reserved-by-this-order counts as available to itself).

*Note:* "Reserved by …" here means the **period-aware rental commitment** (the same basis
as `_get_unavailable_qty`), not merely current stock reservations — that is what lets it
correctly absorb units currently at a customer without a separate, period-blind line.

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
- **RAV-05** Show, for the picking warehouse + period, an accounting flow:
  **Total stock** − **Reserved by other orders** − **In Repair** (if repair installed)
  = **Available for Rent**; then **of which reserved for this order**. Available for Rent
  equals the native availability figure (§0.9). No "At Customer" line in this
  *availability* section — those units are already inside the reserved figures (§0.8).
- **RAV-14** Below it, a **physical partition by current on-hand** that sums to Total:
  warehouse locations (Input/QC/Stock…), **At customer**, **In repair**, and a small
  reconciling **Other / in transit** bucket (§0.11). Uses current quants (robust, ≥ 0) —
  not a per-location pickup forecast (which produced phantom/negative buckets). Keeps
  Total a stable anchor; period-awareness lives in "Available for Rent".
- **RAV-06** Repairs get an explicit line (only when repair installed).
- **RAV-07** Read-only; adds no blocking behaviour.
- **RAV-13** The **Reserved by this order** and **Reserved by other orders** lines are
  always shown (rental storable lines), making the own-demand handling auditable.

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
| T-08 | test_breakdown_is_consistent | Pickable = usable on-hand − reserved-by-others − in-repair; no double-count of at-customer units | RAV-05 |
| T-13 | test_at_customer_not_double_counted | a unit out at a customer for another order is reflected once (via reserved-by-others), and a future period it returns in time for is not reduced | §0.8 |
| T-09 | test_repair_not_installed_no_crash | with repair absent (simulated), availability computes and no repair UI/deduction | RAV-04 |
| T-10 | test_non_rental_untouched | non-rental sale line availability unchanged | RAV-12 |
| T-11 | test_existing_set_availability_regression | prior rental_set set-availability tests still pass (no regression) | G3 |
| T-12 | test_reservation_split_shown | pop-up exposes Reserved-by-this-order and Reserved-by-other-orders with correct values | RAV-13 |

*Note:* existing rental_set availability tests will be **re-run and adjusted** where the
figure legitimately changes (repair deduction, cap fix); any that encoded the old capped
behaviour will be updated to the corrected expectation, documented in the commit.

# 8. Out of Scope / Deferred
- Rewriting the native forecast to a usable-location min-over-period engine (kept native).
- Any change to native padding/preparation-time logic.
- Cleaning/QC as an explicit rentability gate beyond pop-up visibility (a return-route
  location step, tracked separately).
