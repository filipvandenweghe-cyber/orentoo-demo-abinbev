# Sale Flow — Rental Return (Receipt) Demand
*Functional & Technical Requirements, Goals & Tests — Backend / Sales (Rental) + Inventory (v1, FINAL)*

| | |
|---|---|
| **Project** | Orentoo — Odoo 19.0 (Odoo.sh) |
| **Module** | sale_flow |
| **Where** | `services/sale_flow_sync_service.py` → `_reconcile_return_pickings` |
| **Trigger** | Every picking validation (`stock.move._action_done` → `_sync_moves_to_flow`) |
| **Author** | Pro-Designed.com |
| **Status** | Implemented, tested & verified on dev |
| **Date** | 2026-09-01 |

# 1. Purpose & Business Context
When a rental is delivered, a **return picking ("receipt")** anticipates the goods coming
back. Its demand must equal **what the customer actually has to return**. Getting this
wrong causes two visible problems: a **wrong receipt quantity**, and a **phantom
Forecasted‑Report figure** (the return moves feed Odoo's native `virtual_available`).

# 2. Background & Root-Cause (verified in code)
`_reconcile_return_pickings` runs on **every** picking `_action_done` and rewrote the
return demand. Originally it computed `expected = delivered + Σ(pending outbound moves)`.
In a multi‑step delivery route (`Pick → Pack → Ship`) **the same units appear as a move on
every leg**, so summing the pending moves **double/triple‑counted** them:

```
confirm          receipt 4
validate PICK    receipt 8    ← +4 (same units, counted again)
validate PACK    receipt 12   ← +4
validate SHIP    receipt 4    ← collapses to delivered
```
Reproduced on a **plain, non‑set** product, so it was **not** rental_set and **not** native
Odoo — it was this module's leg‑summing. (S00703 / S01788 were the field reports.)

# 3. Design Decision — Options & final rule
Several formulations were tried and reproduced:
1. `current_qty` (ordered) — stable across steps, but **missed over‑delivery** (S01788: ordered 5, delivered 7 → must expect 7).
2. `max(current_qty, delivered)` — fixed over‑delivery, but **missed a pending back‑order** that exceeds the order (S00703).
3. Origin leg (units that left Stock) — robust for multi‑step / over‑delivery / back‑order, but **over‑counts an over‑pick left stranded** in the warehouse (never shipped).

**Final decision — Option B: the receipt = what has actually gone OUT to the customer.**
> "Until it is out, the client is not expected to return it."

`expected return = Σ of DONE outbound moves whose destination reached the customer /
rental location` (per product). A **guard** leaves the return untouched while a delivery is
still in progress (nothing shipped yet + outbound still pending), so the return picking is
**not cancelled mid‑multi‑step**; it is only reduced/cancelled once nothing more is coming.

# 4. Goals
- **G1** Receipt equals what the customer actually holds (delivered‑to‑customer), never inflated by internal warehouse legs.
- **G2** Over‑delivery is expected back in full.
- **G3** Over‑pick that is never shipped is **not** expected (no special undo — just don't ship it, or put it back).
- **G4** A **pending** back‑order is not expected until it ships; then it is added.
- **G5** No churn: the return picking is not cancelled/recreated while a delivery is in progress.

# 5. Functional Requirements
- **SFR-01** On outbound validation, set each rental product's return demand to the sum of
  **done** outbound moves that reached the customer/rental location.
- **SFR-02** Intermediate legs (to Packing/Output — internal warehouse locations) do **not**
  count → multi‑step never inflates the receipt (it grows only as goods ship).
- **SFR-03** Over‑delivery: whatever shipped is expected back (ship 7 on a 5‑line → 7).
- **SFR-04** Over‑pick not shipped: excess stays in the warehouse → not expected; the
  moment it ships it becomes expected, if put back it simply returns to stock.
- **SFR-05** Back‑order: pending part not expected until shipped; then added.
- **SFR-06** While delivery is in progress and nothing has reached the customer yet, leave
  the return demand as‑is (do not cancel the return picking).
- **SFR-07** Only rental orders (`is_rental_order`) with return pickings are affected; sale
  products untouched.

# 6. Interaction with availability (rental_set)
Consistent single trigger — **"out to the customer"**: crossing into the customer/rental
location is the one event that (a) makes a unit "expected back" (this module) and (b) moves
it from warehouse availability to at‑customer (rental_set). Units in warehouse locations
(Stock/Packing/Output) remain **present in stock** and do not add return demand.

# 7. Tests (`sale_flow/tests/test_sale_flow.py`)
| # | Test | Verifies | Req |
|---|---|---|---|
| test_17 | partial delivery, no back‑order | receipt = delivered (2 of 3) | SFR-01 |
| test_23 | multi‑step Pick→Pack→Ship | receipt never inflates across legs (stays 4) | SFR-02 |
| test_24 | over‑delivery (ship 7 on 5‑line) | receipt = 7 | SFR-03 |
| test_32 | back‑order | pending → receipt 2; after it ships → 3 | SFR-05 |
| test_33 | over‑pick 8, ship only 5 | receipt = 5 (3 unshipped not expected) | SFR-04 |

All `sale_flow` tests green on the dev DB against the full Enterprise addons path.

# 8. Out of Scope / Notes
- The native **Forecasted Report** is standard Odoo; it now reads correct return moves, so
  its transient inflation is gone.
- The one lens caveat: while over‑picked units sit **staged** in Packing/Output for a
  delivery, availability still treats them as ordinary present stock (physical‑presence
  lens); they convert to "expected back" only when they actually ship.
