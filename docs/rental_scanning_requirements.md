# Rental Scanning — Prepared-Package & Set Picking
*Functional & Technical Requirements — Backend / Inventory + Barcode (v3, FINAL)*

| | |
|---|---|
| **Project** | Orentoo — Odoo 19.0 (Odoo.sh) |
| **Module (proposed)** | rental_scanning — home for all future barcode/scanning work |
| **Depends on** | stock, stock_barcode (Enterprise); composes with rental_set |
| **Channel** | Backend / Inventory + Barcode only — NOT visible in Sales/Website |
| **Languages** | Multilingual: English source + Dutch (nl) & French (fr) translations |
| **Author** | Pro-Designed.com |
| **Status** | Final analysis — approved; implementation not started (no code yet) |
| **Date** | 2026-08-28 |

# 1. Purpose & Business Context
Warehouse staff prepare sets (combined products) into physical packages ahead of orders to speed up picking. Which prepared package serves which order is decided only at pick time ("late binding"), by manually scanning or selecting the package on the operation. This document specifies that behaviour and records WHY each decision was taken. Preparation (building packages) is done manually with standard Odoo tools.
# 2. Confirmations (verified in code)
- Multi-step routes: the rental-set logic is NOT gated by operation type. Grouping, the "[Set] Product" prefix, indentation and the zero-demand header work identically on Pick, Pack, Ship and single-step Delivery. (Keys off "outbound sale chain": sale_id set AND return_id not set.)
- Set header disappears at the client: grouping and the header show ONLY on the outbound sale chain. Return pickings (return_id set) show NO header and NO prefix, because the warehouse cannot control how the client returns goods. So once goods reach the client and come back, the set-header is gone and items return as plain products. (Verified in _compute_rental_set_show_grouping and _compute_description_picking.)
# 3. Design Decisions & Rationale
This section records what was chosen, what was rejected, and why — for future maintainers.

| Decision | Chosen | Rejected alternative(s) | Why |
|---|---|---|---|
| D-01 Manual late binding (Option A) | Scan/select a prepared package at pick time. | Auto-reserve a matching package (Option B). | You do not know which package serves which order until picking; manual selection is closest to Odoo standard. Auto-reservation adds significant matching logic and edge cases; deferred, can be layered later. |
| D-02 Container = generic package, reconciled by ACTUAL contents | Read the package's real quants and match them to demand. | Infer contents/"the set" from the container or its crate serial (old Approach B). | A crate is reusable and its contents vary (40 glasses today, 40 plates tomorrow). The identity of the box therefore says nothing about what is inside; only the live contents are trustworthy. |
| D-03 Returnable container = serial-tracked PRODUCT | Model the crate (Eurobak 40) as a serial-tracked product. | A custom "returnable packaging" object; forcing package-ID = serial. | Odoo has no first-class returnable-transport-packaging. The standard pattern is a tracked/rented product; it gives per-crate delivery/return identity natively and is counted like any product. Coupling a package name to a serial fights the generic/reusable model and needs custom code. |
| D-04 Option (iii): package dissolves at delivery; serial is the durable label | The serial-tracked crate itself travels to the client and returns, so it IS the reusable label. | (ii-a) disposable box that travels; (ii-b) reusable box + custom override to travel. | The crate serial already provides "travels + reused" from the product side, with per-crate identity, and needs almost no customization. (ii-a) has no reuse lifecycle and clutters customer locations; (ii-b) adds custom code to make a reusable box travel — unnecessary. |
| D-05 Serial-scan is equivalent to package-scan | Scanning a content serial resolves to the package that currently holds it and picks that package's actual contents. | Serial-scan drives a set definition. | Contents-driven resolution stays truthful when contents vary; Odoo can natively find which package holds a serial. Driving a set from a serial was rejected under D-02. |
| D-06 Set-scan is a separate, definition-driven feature | Scanning a set barcode fills the set's expected components (PPB-12); no physical package needed. | Merge set-scan and container-scan into one. | They solve different needs: container-scan reflects physical truth; set-scan fills demand when no prepared box exists. Keeping them separate avoids conflating physical contents with a template. |
| D-07 Overflow → ask to split (not hard-fail) | If a package holds more than needed, prompt the picker to split. | Silently split, or hard-reject. | Removing items from a package is real physical work that must be acknowledged; a prompt is more elegant than a blunt error and prevents silent, invisible splitting. |
| D-08 Extra stock must be added manually | If more than the package is genuinely needed, the picker adds a line explicitly. | Auto-pull extra from the package/stock. | Keeps additions explicit and auditable; prevents the demand-0 overflow seen previously. |
| D-09 Works on ANY operation type | Outbound, internal and inbound. | Restrict to outbound only. | The same regrouping is useful on inbound (e.g. regroup returned products into packages before moving to stock). No reason to gate by operation type. |
| D-10 One module: rental_scanning | A single barcode module, depending only on stock_barcode. | Put it inside rental_set; or many tiny modules. | The feature is generic (works for non-set pickings too) and must not force an Enterprise (stock_barcode) hard-dependency onto rental_set. One module is the home for future scanning work; split only when a different dependency footprint appears. |
| D-11 Reuse native reusable package types | Lean on package_use = "reusable" for scan-adds-contents and empty-after-use. | Build a custom "reusable label" field / mechanism. | Native behaviour already covers scan-adds-contents and freeing the box; a custom metadata field was dropped as redundant. Keeps packages generic. |
| D-12 Multilingual (en + nl + fr) | Ship translations. | English-only. | Belgian operation; warehouse staff use Dutch/French. |

# 4. Standard Odoo Mechanisms Reviewed

| Mechanism | Relevance |
|---|---|
| Reusable package type | package_use = "reusable": scanning a reusable box adds its products; the box is emptied afterwards and reused. Basis for D-11. |
| Box freed after use | _check_entire_pack attaches a DISPOSABLE box to the goods (it travels) but leaves a REUSABLE box behind (it stays and is reused). Basis for D-04. |
| Serial / lot tracking | A package's quants carry lot_id; delivery/return are verified per serial/lot. Basis for D-03/D-05. |
| Kits / phantom BoM | Explodes a product into components on delivery — same idea as our sets; no need to switch. |
| Product packaging (UoM) | "Sell in packs of N" as a UoM — different concept, not used. |
| Returnable container | No first-class object; standard practice is a tracked product (D-03). |

# 5. Container & Returnable-Packaging Model (final)
- The container is a generic stock.package; picking is reconciled against its ACTUAL contents (never a set). Contents may include serial/lot-tracked items (the crate) and untracked items (glasses).
- The returnable crate is a serial-tracked PRODUCT (Eurobak 40). Its serial is the durable, reusable identity: delivered to the client, returned, re-packed next cycle, counted like any product.
- Option (iii): at delivery the stock.package dissolves; the crate serial + glasses go to the client as products. The physical crate (the serial) provides the "travels + reused" behaviour; no traveling-package customization is required.
- Serial-scan is equivalent to package-scan: scanning the crate serial resolves to its current package and picks that package's actual contents.
- Ad-hoc containers are supported alongside pre-prepared ones (native Put in Pack); same reconciliation.
*Caveats (accepted): serial-scan only behaves as a "container" while the crate is actually packed; container-at-customer traceability is via the delivery record + serial, not a live package object; glasses are fungible so their return is verified by count while the crate is verified per-serial.*
# 6. Functional Requirements

| ID | Title | Requirement |
|---|---|---|
| PPB-01 | Scan/assign | On any picking, the user can scan a package barcode (Barcode app) or select it via a backend action to assign it. Native reusable package types make scan-adds-contents work; the rules below are layered on top. |
| PPB-02 | Location rule (all locations) | A package is eligible only if it is in (a sublocation of) the picking's source location — same rule as normal picking, for ALL locations. |
| PPB-03 | Reconcile actual contents | For each product in the package that matches an OPEN demand, fill the move-line done-qty from the package and stamp the source package (and its lot/serial for tracked items). Never create demand-0 lines. Reconcile by ACTUAL contents, never an inferred set. |
| PPB-04 | No silent overflow | The scan never exceeds demand silently (fixes the "demand 0 / 40 / 80" doubling). |
| PPB-05 | Exact-fit + manual add | Accepted when every product+qty fits within remaining demand. If extra stock is genuinely required, the picker adds a line MANUALLY (explicit, never auto-pulled). |
| PPB-06 | Overflow → ask to split | If the package holds MORE of a product than needed, prompt the picker to split: yes = consume up to demand and keep the remainder; no = reject. Splitting is real physical work and must be acknowledged. |
| PPB-07 | Partial allowed | If the package covers only part of the demand, accept, fill what it can, and leave the rest open for another package or a loose pick. |
| PPB-08 | Set header no-op | The zero-demand set header produces no barcode line and never blocks validation (Validate -> button_validate, where _sanity_check neutralises it). |
| PPB-09 | Any operation type | Works on outbound, internal AND inbound operations (e.g. regroup returned products into packages before moving to stock). Not gated by operation type. |
| PPB-10 | Container lifecycle (Option iii) | The stock.package is warehouse-internal and dissolves at delivery. The serial-tracked container PRODUCT is the reusable, durable identity: delivered, returned, re-packed next cycle. Return verifies the crate per-serial and glasses by count. |
| PPB-11 | Backend parity | A backend "Assign prepared package" action applies the identical reconciliation/validation as the Barcode scan. |
| PPB-12 | Set barcode (definition-driven) | A barcode can be assigned to a SET; scanning it fills the set's DEFINED components (capped, with PPB-05/06 rules). No physical package needed. Separate from the container scan; does not pin specific serials. |
| PPB-13 | Serial-scan -> container | Scanning a tracked content's serial resolves to the package that currently holds it and picks that package's ACTUAL contents — the same result as scanning the package barcode. |
| PPB-14 | Multilingual | All user-facing strings (errors, split prompt, action labels) are translatable; Dutch (nl) and French (fr) translations ship with the English source. |

# 7. Reconciliation Algorithm (scan/assign)
1. Resolve the scanned barcode: a package -> that package; a content serial -> the package holding it (PPB-13); a set barcode -> the set's defined components (PPB-12). Verify PPB-02 location.
1. Read contents as product -> qty (actual package contents, or set components for PPB-12), including lot/serial for tracked items.
1. Compute remaining demand per product on this picking (open moves).
1. For each product: if package_qty <= remaining_demand -> apply (fill move-line, cap at demand, stamp source package + lot/serial). If a product is not demanded at all -> reject with a clear message (add manually per PPB-05 if truly needed).
1. If package_qty > remaining_demand for some product -> prompt "split the package?" (PPB-06).
1. Leave the zero-demand set header untouched; proceed to button_validate; partial demand stays open.
# 8. Acceptance Test Scenarios

| ID | Scenario | Expected result |
|---|---|---|
| T-01 | Exact match, single-step | Package = exact demand -> fills all moves, no overflow, validates. |
| T-02 | Exact match, multi-step | Same on Pick->Pack->Ship -> works each step. |
| T-03 | Extra product | Package has a product not demanded -> rejected; picker may add a line manually. |
| T-04 | Quantity overflow -> split prompt | More of a product than needed -> picker asked to split. |
| T-05 | Partial | Fewer than demanded -> accepted, remainder open. |
| T-06 | Wrong location | Package outside the picking source -> ineligible. |
| T-07 | Set header no-op | Zero-demand header never blocks validation. |
| T-08 | Inbound regroup | On inbound/internal, scanning regroups products into a package. |
| T-09 | Set barcode | Scanning a set barcode fills the set's defined components (PPB-12). |
| T-10 | Serial-scan -> container | Scanning a crate serial picks its current package's contents (PPB-13). |
| T-11 | Serial delivery/return | Crate serial recorded on delivery; return reconciles serial back + glasses by count. |
| T-12 | Multilingual | Error and split-prompt strings appear translated in nl/fr. |

*Today's suite has no physical-package coverage; T-01..T-12 add it.*
# 9. Module Architecture
- Single module rental_scanning, depending only on stock_barcode (+ composes with rental_set). Home for all future scanning work.
- Reuse native reusable package types for scan-adds-contents and box freeing; the module adds the strict-fit rules, the split prompt, serial-scan resolution, the set barcode, and set composition.
- Interference: keep improvements that patch the SAME barcode JS method (e.g. _processPackage) in this one module and compose them in a single patch; always call super().
# 10. Scope Boundaries
**In scope:**
- Manual scan/assign of a package (or crate serial, or set barcode) on any operation.
- Strict-fit reconciliation with split prompt; serial/lot handling; multilingual.
- All routes; set-header no-op; ad-hoc and pre-prepared containers.
**Out of scope (with reason):**
- Automated kitting/preparation build — done manually to keep scope limited.
- Auto-reservation of a matching package (Option B) — deferred; heavy matching logic.
- Sales/Website/Kiosk visibility — this is a warehouse-only concept.
- A new product for the package, or package-ID=serial coupling — rejected (D-03).
- A custom reusable-label metadata field — rejected (D-11); native types suffice.
- Making a package physically travel (Option ii) — rejected (D-04) in favour of the serial.
