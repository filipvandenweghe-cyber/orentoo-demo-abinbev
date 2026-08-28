# Rental Scanning — Prepared-Package & Set Picking
*Functional & Technical Requirements — Backend / Inventory + Barcode (v2)*

| | |
|---|---|
| **Project** | Orentoo — Odoo 19.0 (Odoo.sh) |
| **Module (proposed)** | rental_scanning — home for all future barcode/scanning work |
| **Depends on** | stock, stock_barcode (Enterprise); composes with rental_set |
| **Channel** | Backend / Inventory + Barcode only — NOT visible in Sales/Website |
| **Languages** | Multilingual: English source + Dutch (nl) & French (fr) translations |
| **Author** | Pro-Designed.com |
| **Status** | Draft for approval — implementation not started |
| **Date** | 2026-08-28 |

# 1. Purpose & Business Context
Warehouse staff prepare sets (combined products) into physical packages ahead of orders, to speed up picking. Which prepared package serves which order is decided only at pick time ("late binding"), by manually scanning or selecting the package on the operation. This document specifies that behaviour. Preparation (building packages) is done manually with standard Odoo.
# 2. Confirmations Requested
- Multi-step routes: the rental-set logic is NOT gated by operation type. Set grouping, the component prefix "[Set] Product", indentation and the zero-demand header work identically on Pick, Pack, Ship and single-step Delivery. Verified in code (keys off "outbound sale chain": sale_id set AND return_id not set) — no per-operation-type branch exists.
- Set header disappears at the client: set grouping and the header are shown ONLY on the outbound sale chain. Return pickings (return_id set) show NO header and NO prefix — the warehouse has no control over how the client returns goods. So once goods reach the client and come back, the set-header is gone and items return as plain products. Verified in rental_set (_compute_rental_set_show_grouping and _compute_description_picking both exclude returns).
# 3. Standard Odoo Mechanisms Reviewed (important)
A review of Odoo 19 shows much of this is NATIVE. Findings:

| Mechanism | What Odoo 19 provides |
|---|---|
| Reusable package type | stock.package.type.package_use = "reusable" (vs "disposable"). Odoo help: "Reusable boxes are used for batch picking and emptied afterwards to be reused. In the Barcode application, scanning a reusable box will add the products in this box." → scan-adds-contents is NATIVE. |
| Box freed after use | _check_entire_pack: for entire-pack moves, a NON-reusable box becomes the result_package (travels with the goods); a REUSABLE box is NOT set as result package → it stays behind, emptied and reused. Matches "label reused, contents not fixed to the box". |
| Usable packages in barcode | _get_usable_packages loads reusable packages (and location-less ones) into the Barcode client as available totes to scan. |
| Kits / phantom BoM | A "kit" product explodes into components on delivery (mrp). This is the same idea as our rental_set; we already have sets, so no need to switch. |
| Product packaging (UoM) | Odoo 19 models "sell in packs of N" as a UoM. Different concept — not used here. |
| Batch / cluster picking | Native flow that uses reusable totes to consolidate picks. Confirms totes are first-class in Odoo. |
| Returnable container | Odoo has no dedicated "returnable transport packaging that cycles to the customer and back". The standard, recommended way is to model the returnable container as a TRACKED/RENTED PRODUCT — which we already do (Eurobak 40). |

**Consequence: rental_scanning is a THIN layer. Most of "scan a package → add its contents / box freed after use" is native via reusable package types. The custom parts are: strict demand-fit with a split prompt, the set-barcode virtual package, and making sure it composes with sets.**
# 4. Reusable / Returnable Container Modelling
Two distinct objects — do not conflate them:
- The returnable container is a PRODUCT (e.g. "Eurobak 40"): delivered to the client, held while with the client, returned and counted via the existing rental return flow. This is Odoo's standard way to handle returnable packaging and already satisfies "counted like a product" and "unavailable while at the client, available again on return".
- The stock.package (e.g. BAK01) is a handling LABEL/tote used in the warehouse. Give it a "reusable" package type so scanning it adds its contents and it is freed for reuse after picking. Its contents are NOT fixed — on return a client may repack differently; the tote is generic.
*This resolves the earlier tension: the "with the client / freed only on return / counted" lifecycle belongs to the PRODUCT (Eurobak 40); the reusable TOTE is a warehouse label that is emptied and reused. No new product is required.*
# 5. What Happens to the Package at Customer Delivery (your question)
Three standard options; pick per package type:

| Option | Behaviour |
|---|---|
| (i) Dissolve | Goods delivered loose, package emptied and the label freed immediately. Native for reusable totes (box stays in the warehouse, never goes to the customer). |
| (ii) Travel with goods | The package becomes result_package and physically goes to the customer (native for DISPOSABLE boxes). The label is "occupied" while at the client and only freed when the goods return. This matches PPB-10 if you want the box to leave the warehouse. |
| (iii) Container = product | The returnable container is a product (Eurobak 40) that travels and returns; the stock.package label is only a warehouse grouping and can dissolve (i). RECOMMENDED. |

**Recommendation: Option (iii) — the returnable semantics live on the PRODUCT; the tote is reusable and warehouse-side. If instead you want the physical label itself to leave with the client and return, use Option (ii) with a disposable box type.**
# 6. Functional Requirements

| ID | Title | Requirement |
|---|---|---|
| PPB-01 | Scan/assign | On any picking the user can scan a package barcode (Barcode app) or select it via a backend action to assign it. Reusable package types make scan-adds-contents native; this requirement layers the rules below on top. |
| PPB-02 | Location rule (all locations) | A package is eligible only if it is in (a sublocation of) the picking's source location — the same rule as normal picking, for ALL locations (WH/Stock was only an example). A package that "looks like a location" is picked when its location is the (pre)selected source. |
| PPB-03 | Reconcile demand | For each product in the package matching an OPEN demand, fill the move-line done-qty from the package and stamp the source package. Never create demand-0 lines. |
| PPB-04 | No silent overflow | The scan never exceeds demand silently (fixes the "demand 0 / 40 / 80" doubling seen earlier). |
| PPB-05 | Exact-fit + manual add | Accepted when every product+qty in the package fits within the remaining demand. If EXTRA stock is genuinely required, the picker must MANUALLY ADD a line for it (so adding extra is possible, but explicit — never automatic from the package). |
| PPB-06 | Overflow → ask to split | If the package holds MORE of a product than is needed, do not hard-fail: ASK the order picker whether they want to split the package. If yes, consume up to demand and leave the remainder in (a) the package; if no, reject the scan. Splitting is real physical work, so it is an explicit, acknowledged action. |
| PPB-07 | Partial allowed | If the package covers only part of the demand, accept, fill what it can, and leave the rest open for another package or a loose pick. |
| PPB-08 | Set header no-op | The zero-demand set header produces no barcode line and never blocks validation (Validate → button_validate, where _sanity_check neutralises it). |
| PPB-09 | Any operation type | Works on ANY warehouse operation — outbound, internal AND inbound. e.g. on inbound it can be a step to regroup returned products into packages before moving to stock. Not gated by operation type. |
| PPB-10 | Container lifecycle | With a reusable tote (Option iii) the tote is freed after picking; the returnable CONTAINER (product) is unavailable while at the client and freed/counted on return. If Option (ii) is chosen, the package label is freed only upon return. |
| PPB-11 | Backend parity | A backend "Assign prepared package" action applies the identical reconciliation/validation as the Barcode scan. |
| PPB-12 | Set barcode (virtual package) | A barcode can be assigned to a SET. Scanning it behaves as if a package containing exactly the set's components were picked: it fills the set's component demand (capped, with the same PPB-05/06 rules). No physical package needed — the set definition acts as the "expected contents". |
| PPB-13 | Multilingual | All user-facing strings (errors, the split prompt, action labels) are translatable; Dutch (nl) and French (fr) translations are shipped alongside the English source. |

# 7. Reconciliation Algorithm (scan/assign)
1. Resolve the scanned package/set-barcode; verify PPB-02 (location). If ineligible → reject.
1. Read contents as product→qty (package contents, or the set's component quantities for PPB-12).
1. Compute remaining demand per product on this picking (open moves).
1. For each product: if package_qty ≤ remaining_demand → apply (fill move-line, cap at demand, stamp source package). If a product is not demanded at all → reject with a clear message (PPB-05 says add it manually if truly needed).
1. If package_qty > remaining_demand for some product → prompt "split the package?" (PPB-06): yes = consume up to demand and keep the remainder; no = reject.
1. Leave the zero-demand set header untouched; proceed to button_validate; partial demand stays open.
# 8. Acceptance Test Scenarios

| ID | Scenario | Expected result |
|---|---|---|
| T-01 | Exact match, single-step | Package = exact demand → fills all moves, no overflow, validates. |
| T-02 | Exact match, multi-step | Same on Pick→Pack→Ship → works each step. |
| T-03 | Extra product | Package has a product not demanded → scan rejected; picker may add a line manually. |
| T-04 | Quantity overflow → split prompt | More of a product than needed → picker is asked to split; yes consumes up to demand, no rejects. |
| T-05 | Partial | Fewer than demanded → accepted, remainder open. |
| T-06 | Wrong location | Package outside the picking source → ineligible. |
| T-07 | Set header no-op | Zero-demand header never blocks validation. |
| T-08 | Inbound regroup | On an inbound/internal operation, scanning regroups products into a package. |
| T-09 | Set barcode | Scanning a set barcode fills the set's component demand (PPB-12). |
| T-10 | Reusable tote freed | After picking, a reusable tote is emptied/freed; a returnable container product is counted on return. |
| T-11 | Multilingual | Error and split-prompt strings appear translated in nl/fr. |

*Today's suite has no physical-package coverage; T-01..T-11 add it.*
# 9. Module Architecture
- Single module rental_scanning, depending only on stock_barcode (+ composes with rental_set). It is the home for all future scanning work.
- Reuse native reusable package types for scan-adds-contents and box-freeing; the module adds only the strict-fit rules, the split prompt, the set barcode, and set composition.
- Interference: keep improvements that patch the SAME barcode JS method (e.g. _processPackage) in this one module and compose them in a single patch; always call super().
# 10. Scope Boundaries & Open Items
- Out of scope: automated kitting build, auto-reservation of a matching package, Sales/Website/Kiosk visibility, a new product for the package.
- "Reusable-label metadata" (from v1) meant a custom field on a package to record "the set it usually holds". This is now DROPPED — native reusable package types + PPB-12 cover it; packages stay generic.
- Decision needed: Option (ii) vs (iii) for whether the physical label leaves with the client (recommended: iii).
