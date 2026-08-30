# Rental Availability — Repairs, Sets & Warehouse Breakdown
*Functional & Technical Requirements, Goals & Tests — Backend / Sales (Rental) + Inventory (v1, for approval)*

| | |
|---|---|
| **Project** | Orentoo — Odoo 19.0 (Odoo.sh) |
| **Module (proposed)** | rental_availability |
| **Depends on** | sale_stock_renting (rental + stock), repair, rental_set |
| **Channel** | Rental order line availability + its pop-up; composes with rental_set |
| **Author** | Pro-Designed.com |
| **Status** | Requirements — for approval; no code yet |
| **Date** | 2026-08-30 |

# 1. Purpose & Business Context
When a rental order line is quoted, staff need a **trustworthy "available for this
period" figure** and a way to **see where the stock actually is**. Two gaps in the
standard behaviour cause wrong numbers and confusion:

1. **Repairs are invisible to availability.** A unit that is broken and sitting in a
   repair order is physically in the warehouse but **not rentable** — yet standard
   availability still counts it. Rentals get quoted against stock that cannot ship.
2. **The availability figure is a single opaque number.** Staff cannot see that, say,
   of 10 units, 3 are at a customer, 2 are in QC (not yet put away), and 1 is in
   repair — so only 4 are truly pickable.

Separately, **set availability** (rental_set) is computed with custom own-demand and
competing-demand math that is fragile and has produced wrong figures. It should lean on
the **native component availability** (which already handles own-demand via
`ignored_soline_id`) and simply take the limiting component.

# 2. Background & Root-Cause (verified in code)
- **Native rental availability** (`sale_stock_renting`,
  `sale.order.line._compute_qty_at_date`): for a start date ≤ now it uses
  `product.with_context(from_date, to_date, warehouse_id).qty_available`; for a future
  start it uses `virtual_available` at the first day. Other rentals are subtracted via
  `product._get_unavailable_qty(from_date, to_date, ignored_soline_id=line.id,
  warehouse_id=...)`. **Own demand is already excluded natively** by
  `ignored_soline_id` — no manual add-back is needed.
- **Warehouse scoping:** with `warehouse_id` in context, `qty_available`/
  `virtual_available` are scoped to the warehouse **view location**, i.e. they include
  **Input + Quality Control + Stock** (multi-step reception siblings). QC/Input stock is
  not yet rentable, so the raw figure can **over-count** during multi-step reception.
- **Repairs:** `repair.order.move_id` (the stock move for the repaired product) is
  **only created in `action_repair_done`**. While a repair is `confirmed`/`under_repair`
  there is **no move**, so `_get_unavailable_qty` and the forecast **never deduct it**.
  Fields available: `product_id`, `lot_id`, `product_qty`, `state`, `create_date`,
  `schedule_date`, `location_id`.
- **Set availability** (`rental_set.sale.order.line._compute_set_availability`) collects
  leaf components, then per product does manual own-demand add-back + competing-demand
  subtraction — the fragile logic this work replaces for the availability figure.

# 3. Design Decisions — Options, Pros/Cons & Rationale
## 3.1 The multi-step over-count (QC/Input not rentable)
**Option A — Rewrite availability to a min-over-period forecast at the usable stock
location only, crediting incoming moves with lead time.**
*Pros:* most accurate.
*Cons:* large custom re-implementation of native forecast; high maintenance; duplicates
Odoo logic that changes between versions.
**Option B — Keep native availability; make the reality *visible* in the pop-up
(per-location breakdown) and rely on standard *padding/preparation time* as the safety
buffer for the reception delay.**
*Pros:* small footprint; no fork of native forecast; padding is standard config that
already exists; staff can see and judge the Input/QC portion.
*Cons:* the headline number can still include not-yet-put-away stock (mitigated by the
breakdown + padding).
**Decision:** **Option B.** Padding stays **standard configuration** — we add **no**
custom padding logic (native padding is expected to change in a future Odoo version, so
it must remain untouched).

## 3.2 Repairs → availability
**Option A — Deduct open repairs from availability over their window.** An open repair
(`state not in ('done','cancel')`) for a product makes `product_qty` unavailable over
`[create_date → schedule_date (or, if overdue, until actually done)]` when that window
overlaps the rental period. The unit stays at its location; deduction is keyed by
product (and lot, for serials).
*Pros:* correct rentable figure; matches the physical truth (broken ≠ rentable).
*Cons:* a small custom availability contribution to maintain.
**Option B — Do nothing / model repair as a stock move up-front.** Rejected: standard
repair creates no move until done, and changing that is invasive.
**Decision:** **Option A.** This is the one genuine availability-math change.

## 3.3 Own-demand for confirmed orders (the old "don't double-count" requirement)
The old customization manually added back the order's own reserved qty for confirmed
lines. Native already excludes own demand via `ignored_soline_id`.
**Decision:** rely on **`ignored_soline_id`**; remove manual own-demand add-back. The
"don't double-count when confirmed" requirement **still holds**, but is satisfied by the
native mechanism, not custom math.

## 3.4 Set availability
**Decision:** set availability = `min over limiting component of
floor( native_component_availability / qty_per_set )`, where
`native_component_availability` is the component line's own
`virtual_available_at_date` (which now includes the repair deduction from §3.2 and
already respects `ignored_soline_id`). Remove the manual own-demand/competing-demand
arithmetic. Non-storable components remain limitless. Nested sets are traversed to leaf
components as today.

## 3.5 Where the code lives
**Decision:** a **new module `rental_availability`** depending on `rental_set` +
`repair`. It (a) adds the repair deduction to native rental availability, (b) extends
the availability pop-up, and (c) overrides `rental_set`'s set-availability compute to the
§3.4 formula. Keeping it separate leaves `rental_set` stable and makes the availability
concern removable/toggleable.

# 4. Goals
- **G1** Availability excludes units in open repair over the repair window.
- **G2** The availability pop-up shows a clear breakdown so staff see *where* stock is
  and what is pickable now.
- **G3** Set availability is the limiting component's whole-set count, using native
  component availability (no fragile custom own-demand math).
- **G4** No custom padding logic — standard preparation/padding config only.
- **G5** No double-counting of the order's own demand (via `ignored_soline_id`).
- **G6** Small, isolated footprint; native forecast is not forked.

# 5. Functional Requirements
## 5.1 Repair-aware availability (RAV-01…03)
- **RAV-01** For a rental line, availability is reduced by the quantity of the product
  tied up in **open** repair orders (`state not in ('done','cancel')`) whose window
  `[create_date → schedule_date, extended to now if overdue]` overlaps the rental
  period.
- **RAV-02** For serial-tracked products, a repair on a specific `lot_id` removes that
  one unit; for qty products, `product_qty` is removed.
- **RAV-03** Repairs already `done`/`cancel` do not reduce availability (the unit is
  either back in stock or gone via recycle/scrap).

## 5.2 Availability pop-up breakdown (RAV-04…06)
- **RAV-04** The rental line availability pop-up shows, for the picking warehouse and
  period:
  - **Total on-hand** (with a per-internal-location split, e.g. Input / Quality Control
    / Stock), so not-yet-put-away stock is visible;
  - **At Customer** (rented out / not yet returned);
  - **In Repair** (open repairs, per RAV-01);
  - **Pickable** = the net figure staff can actually ship now.
- **RAV-05** Repairs get **explicit attention** in the pop-up (own line/section), since
  they typically remain in place and are otherwise invisible.
- **RAV-06** The pop-up remains read-only and adds no blocking behaviour.

## 5.3 Set availability (RAV-07…08)
- **RAV-07** For a set line, availability = `min over leaf components of
  floor( component.virtual_available_at_date / cumulative_qty_per_set )`.
- **RAV-08** Non-storable components are limitless; a set of only non-storable
  components is fully available. Nested sets traverse to leaves. Own demand is handled by
  `ignored_soline_id` — no manual add-back.

## 5.4 Non-goals / guards (RAV-09…10)
- **RAV-09** Padding/preparation time is **standard config**; this module adds none.
- **RAV-10** Only rental orders (`is_rental_order`) and storable products are affected;
  ordinary sale lines are untouched.

# 6. Technical Approach (proposed)
- **Repair contribution:** a helper (e.g. `product.product._get_repair_unavailable_qty(
  from_date, to_date, warehouse_id, lot_id=…)`) summing open-repair `product_qty` whose
  window overlaps `[from_date, to_date]`. Subtract it in an override of
  `sale.order.line._compute_qty_at_date` (after `super()`), lowering
  `virtual_available_at_date`/`free_qty_today`.
- **Pop-up:** extend the native `qty_at_date_widget` (OWL) template + its data source
  (add breakdown fields computed server-side: on-hand per internal location, at-customer,
  in-repair, pickable). Purely presentational.
- **Set availability:** override `rental_set._compute_set_availability` to the §3.4
  formula, reading each leaf's `virtual_available_at_date` (repair-aware) instead of the
  manual math.

# 7. Tests (proposed `tests/test_rental_availability.py`)
| # | Test | Verifies | Requirement |
|---|---|---|---|
| T-01 | test_open_repair_reduces_availability | an open repair over the period lowers the line's availability by product_qty | RAV-01 |
| T-02 | test_done_repair_does_not_reduce | a `done` repair does not reduce availability | RAV-03 |
| T-03 | test_repair_outside_period_ignored | a repair whose window doesn't overlap the rental period has no effect | RAV-01 |
| T-04 | test_serial_repair_removes_one_unit | a repair on a serial removes exactly that unit | RAV-02 |
| T-05 | test_set_availability_limiting_component | set availability = floor(min component avail / qty-per-set) | RAV-07 |
| T-06 | test_set_non_storable_limitless | non-storable components don't constrain the set | RAV-08 |
| T-07 | test_own_demand_not_double_counted | a confirmed order's own demand doesn't reduce its own availability (ignored_soline_id) | RAV-05/G5 |
| T-08 | test_breakdown_values | pop-up breakdown numbers sum consistently (total − at-customer − in-repair ≈ pickable) | RAV-04 |
| T-09 | test_non_rental_untouched | a non-rental sale line's availability is unchanged | RAV-10 |

# 8. Out of Scope / Deferred
- Rewriting the native forecast to a usable-location min-over-period engine (§3.1 Opt A).
- Any change to native padding/preparation-time logic (§3.1, RAV-09).
- Cleaning/QC as an explicit rentability gate beyond the pop-up's visibility (handled by
  a location step in the return route, tracked separately).
