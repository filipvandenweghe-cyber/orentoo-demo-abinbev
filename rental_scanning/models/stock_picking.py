from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class StockPicking(models.Model):
    """Prepared-package / set / serial scanning for pickings.

    Central entry point: ``rental_scanning_scan(barcode, allow_split=False)``.

    The scan is reconciled against the picking's OPEN demand — it never
    creates demand-0 overflow lines and never infers a set from a container
    (see docs/rental_scanning_requirements, PPB-01..14).

    Important semantics (Odoo 19): on a reserved ("Ready") picking the
    reservation is stored as ``move.line.quantity`` with ``picked = False``.
    Such reserved-but-not-picked lines are treated here as *available
    capacity* to be re-pointed at the scanned package — NOT as already
    fulfilled.  Only ``picked = True`` lines count as fulfilled.
    """

    _inherit = 'stock.picking'

    # Source packages currently applied (picked) on this transfer — shown on
    # the form so an applied package is visible at a glance (Q1 / PPB-16).
    rental_scanning_package_ids = fields.Many2many(
        'stock.package',
        string='Scanned Packages',
        compute='_compute_rental_scanning_package_ids',
        help="Source packages currently picked on this transfer via scanning.",
    )

    @api.depends('move_line_ids.package_id', 'move_line_ids.picked',
                 'move_line_ids.quantity')
    def _compute_rental_scanning_package_ids(self):
        for picking in self:
            picking.rental_scanning_package_ids = picking.move_line_ids.filtered(
                lambda l: l.picked and l.package_id and l.quantity
            ).mapped('package_id')

    # ── helpers ──────────────────────────────────────────────────────────────

    def _rs_precision(self):
        return self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')

    @staticmethod
    def _rs_fmt(value):
        return ('%g' % value)

    def _rs_open_moves(self, product_id=None):
        """Open (not done/cancel) moves, optionally filtered by product."""
        self.ensure_one()
        moves = self.move_ids.filtered(
            lambda m: m.state not in ('done', 'cancel')
            and m.product_uom_qty > 0
        )
        if product_id is not None:
            moves = moves.filtered(lambda m: m.product_id.id == product_id)
        return moves

    def _rs_demand_for(self, product_id):
        """Total demand for a product across open moves."""
        return sum(self._rs_open_moves(product_id).mapped('product_uom_qty'))

    def _rs_picked_other(self, product_id, package):
        """Quantity already PICKED for this product from a source OTHER than
        ``package`` (real fulfilment we must preserve).  Lines sourced from
        ``package`` are excluded so that re-scanning the same package is
        idempotent."""
        total = 0.0
        for move in self._rs_open_moves(product_id):
            for line in move.move_line_ids:
                if line.picked and not (package and line.package_id == package):
                    total += line.quantity
        return total

    def _rs_remaining(self, product_id, package):
        """How much of ``product_id`` still needs to be picked, treating any
        prior pick from ``package`` as replaceable (idempotent re-scan)."""
        remaining = self._rs_demand_for(product_id) \
            - self._rs_picked_other(product_id, package)
        return max(remaining, 0.0)

    # ── content extraction ───────────────────────────────────────────────────

    def _rs_contents_from_package(self, package):
        """Return contents from a package's quants.

        ``src_package_id`` is the quant's ACTUAL (innermost) package so that
        nested/general packs stamp the correct source package on each line.
        """
        prec = self._rs_precision()
        contents = []
        for quant in package.contained_quant_ids:
            if quant.quantity < 0 \
                    or float_is_zero(quant.quantity, precision_digits=prec):
                continue
            contents.append({
                'product_id': quant.product_id.id,
                'qty': quant.quantity,
                'lot_id': quant.lot_id.id or False,
                'src_package_id': quant.package_id.id or package.id,
            })
        return contents

    def _rs_contents_from_set(self, set_product):
        """Return flattened set components as contents (no lots/packages)."""
        result = []
        self.env['product.template']._collect_leaf_components_for_availability(
            set_product.product_tmpl_id, 1.0, result)
        return [
            {'product_id': product.id, 'qty': qty, 'lot_id': False,
             'src_package_id': False}
            for product, qty in result
        ]

    def _rs_group_contents(self, contents):
        """Group content lines by product -> [(qty, lot_id, src_package_id)]."""
        grouped = defaultdict(list)
        for c in contents:
            grouped[c['product_id']].append(
                (c['qty'], c['lot_id'], c.get('src_package_id', False)))
        return grouped

    # ── barcode resolution ───────────────────────────────────────────────────

    def _rs_resolve_barcode(self, barcode):
        """Resolve a scanned barcode.

        Returns a tuple ``(kind, record, contents)`` where kind is one of
        'package' / 'set' / 'product', or ``(False, False, [])`` if unknown.
        A *packed* serial resolves to its package; a *loose* serial resolves
        to a single-serial product add (PPB-13).
        """
        self.ensure_one()
        barcode = (barcode or '').strip()
        if not barcode:
            return (False, False, [])

        Package = self.env['stock.package']
        Lot = self.env['stock.lot']
        Product = self.env['product.product']

        # 1) A physical package by reference
        package = Package.search([('name', '=', barcode)], limit=1)
        if package:
            return ('package', package, self._rs_contents_from_package(package))

        # 2) A lot / serial number
        lot = Lot.search([('name', '=', barcode)], limit=1)
        if lot:
            quant = self.env['stock.quant'].search([
                ('lot_id', '=', lot.id),
                ('package_id', '!=', False),
                ('quantity', '>', 0),
            ], limit=1)
            if quant.package_id:
                pkg = quant.package_id
                return ('package', pkg, self._rs_contents_from_package(pkg))
            return ('product', lot.product_id,
                    [{'product_id': lot.product_id.id, 'qty': 1.0,
                      'lot_id': lot.id, 'src_package_id': False}])

        # 3) A product barcode -> set (definition-driven) or plain product
        product = Product.search([('barcode', '=', barcode)], limit=1)
        if product:
            if product.is_rental_set:
                return ('set', product, self._rs_contents_from_set(product))
            return ('product', product,
                    [{'product_id': product.id, 'qty': 1.0, 'lot_id': False,
                      'src_package_id': False}])

        return (False, False, [])

    # ── eligibility (PPB-02) ─────────────────────────────────────────────────

    def _rs_check_package_location(self, package):
        """A package is eligible only if it is at (a sublocation of) the
        picking's source location.  Location-less packages are allowed."""
        self.ensure_one()
        loc = package.location_id
        if not loc:
            return
        source = self.location_id
        ok = loc == source or (
            loc.parent_path and source.parent_path
            and loc.parent_path.startswith(source.parent_path))
        if not ok:
            raise UserError(_(
                "Package %(pkg)s is located in %(loc)s, which is not part of "
                "the source location %(src)s of this operation.",
                pkg=package.name, loc=loc.display_name,
                src=source.display_name,
            ))

    # ── validation & messaging ───────────────────────────────────────────────

    def _rs_validate_fit(self, grouped, package):
        """Return (not_demanded, overflow).

          not_demanded = [product_id, ...]           (absent from the order)
          overflow     = [(product_id, have, need)]  (more than still needed)
        """
        prec = self._rs_precision()
        not_demanded, overflow = [], []
        for product_id, entries in grouped.items():
            have = sum(q for q, _lot, _pkg in entries)
            demand = self._rs_demand_for(product_id)
            if float_compare(demand, 0.0, precision_digits=prec) <= 0:
                not_demanded.append(product_id)
                continue
            need = self._rs_remaining(product_id, package)
            if float_compare(have, need, precision_digits=prec) > 0:
                overflow.append((product_id, have, need))
        return not_demanded, overflow

    def _rs_overflow_message(self, overflow):
        Product = self.env['product.product']
        parts = []
        for product_id, have, need in overflow:
            parts.append(_(
                "- %(name)s: package has %(have)s but only %(need)s still "
                "needed (%(excess)s too many)",
                name=Product.browse(product_id).display_name,
                have=self._rs_fmt(have), need=self._rs_fmt(need),
                excess=self._rs_fmt(have - need),
            ))
        return _(
            "This package holds more than this operation still needs:\n"
            "%(lines)s\n\n"
            "Splitting (opening) the package is real work.  Confirm to take "
            "only what is needed and leave the remainder in the package, or "
            "cancel.",
            lines="\n".join(parts),
        )

    # ── reconciliation core ──────────────────────────────────────────────────

    def _rs_is_internal_step(self, move):
        """True only for a genuine in-warehouse follow-up step (e.g.
        Pick -> Output), i.e. the destination is an internal location that
        belongs to the operation's own warehouse.

        NOT true for the final rental/customer delivery: sale_renting sends
        rented goods to a 'Customers/Rental' location whose usage is
        'internal' but which lives OUTSIDE the warehouse tree — that must
        dissolve (Option iii)."""
        dest = move.location_dest_id
        if dest.usage != 'internal':
            return False
        wh = move.picking_id.picking_type_id.warehouse_id
        view = wh.view_location_id if wh else False
        if not (view and dest.parent_path and view.parent_path):
            return False
        return dest.parent_path.startswith(view.parent_path)

    def _rs_place(self, moves, product_id, to_place, package, retain):
        """Create picked move-lines for ``to_place`` =
        [(qty, lot_id, src_package_id), ...], distributed across ``moves`` and
        capped at each move's remaining (demand minus already-picked).

        PPB-17: retain the scanned ``package`` as the result (destination)
        package ONLY for a genuine in-warehouse internal step AND only when
        the WHOLE package moves (``retain`` — no split/overflow).  Otherwise
        leave it dissolved: no result package (the final customer/rental
        delivery, or any partial scan — a package cannot be split across two
        locations)."""
        prec = self._rs_precision()
        MoveLine = self.env['stock.move.line']
        caps = []
        for move in moves:
            picked_here = sum(
                line.quantity for line in move.move_line_ids if line.picked)
            caps.append([move, move.product_uom_qty - picked_here])

        filled = self.env['stock.move']
        idx = 0
        for qty, lot_id, src_pkg in to_place:
            remaining = qty
            while float_compare(remaining, 0.0, precision_digits=prec) > 0 \
                    and idx < len(caps):
                move, cap = caps[idx]
                if float_compare(cap, 0.0, precision_digits=prec) <= 0:
                    idx += 1
                    continue
                take = min(remaining, cap)
                keep_pack = retain and package \
                    and self._rs_is_internal_step(move)
                MoveLine.create({
                    'move_id': move.id,
                    'picking_id': self.id,
                    'product_id': product_id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'quantity': take,
                    'picked': True,
                    'package_id': src_pkg or (package.id if package else False),
                    'result_package_id': package.id if keep_pack else False,
                    'lot_id': lot_id or False,
                })
                caps[idx][1] = cap - take
                remaining -= take
                filled |= move
        filled.picked = True

    def _rs_apply(self, contents, package=False, allow_split=False):
        """Reconcile ``contents`` against the picking demand.

        Returns:
          {'status': 'applied'}                                consumed fully
          {'status': 'partial'}                                consumed up to demand
          {'status': 'need_split', 'overflow': [...], 'message': str}
        Raises UserError when a product is not on this operation.
        """
        self.ensure_one()
        prec = self._rs_precision()
        grouped = self._rs_group_contents(contents)

        not_demanded, overflow = self._rs_validate_fit(grouped, package)
        if not_demanded:
            names = self.env['product.product'].browse(
                not_demanded).mapped('display_name')
            raise UserError(_(
                "These products are in the package but not required by this "
                "operation: %(names)s.\n"
                "If extra stock is genuinely needed, add a line manually.",
                names=", ".join(names),
            ))
        if overflow and not allow_split:
            return {
                'status': 'need_split',
                'overflow': overflow,
                'message': self._rs_overflow_message(overflow),
            }

        # PPB-17: only retain the package (result package) when the WHOLE
        # package moves — i.e. no overflow/split.  A split would put the same
        # package in two locations, which Odoo forbids.
        retain = bool(package) and not overflow

        for product_id, entries in grouped.items():
            remaining = self._rs_remaining(product_id, package)
            moves = self._rs_open_moves(product_id)

            # Drop the loose reservation (picked=False) and any prior pick
            # from THIS package; keep picks from other sources.
            stale = moves.move_line_ids.filtered(
                lambda l: not l.picked or (package and l.package_id == package))
            stale.unlink()

            if float_compare(remaining, 0.0, precision_digits=prec) <= 0:
                continue

            # Build the placement list, capped at the remaining demand.
            to_place, acc = [], 0.0
            for qty, lot_id, src_pkg in entries:
                if float_compare(acc, remaining, precision_digits=prec) >= 0:
                    break
                place = min(qty, remaining - acc)
                if float_is_zero(place, precision_digits=prec):
                    continue
                to_place.append((place, lot_id, src_pkg))
                acc += place
            self._rs_place(moves, product_id, to_place, package, retain)

        return {'status': 'partial' if overflow else 'applied'}

    # ── public entry point ───────────────────────────────────────────────────

    def rental_scanning_scan(self, barcode, allow_split=False):
        """Scan a package / set / serial and reconcile it against demand.

        Single server entry point for both the backend action (PPB-11) and
        the Barcode client.  Returns the ``_rs_apply`` result dict enriched
        with 'kind' and (for packages) 'package'.
        """
        self.ensure_one()
        kind, record, contents = self._rs_resolve_barcode(barcode)
        if not kind:
            raise UserError(_(
                "Barcode '%(bc)s' was not recognised as a package, set or "
                "serial number.", bc=barcode))

        package = record if kind == 'package' else False
        if package:
            self._rs_check_package_location(package)

        if not contents:
            raise UserError(_(
                "Nothing to add: the scanned %(kind)s is empty.", kind=kind))

        result = self._rs_apply(contents, package=package,
                                allow_split=allow_split)
        result['kind'] = kind
        if package:
            result['package'] = package.id
        return result

    # ── remove / unassign a scanned package (PPB-15) ─────────────────────────

    def rental_scanning_remove_package(self, package):
        """Remove a previously-scanned source package from this transfer.

        Clears the picked move-lines sourced from ``package`` (reverting that
        quantity to open demand) so another package can be scanned instead.
        Does not create a replacement (no 'replace' by design).
        """
        self.ensure_one()
        if isinstance(package, str):
            package = self.env['stock.package'].search(
                [('name', '=', package.strip())], limit=1)
        if not package:
            raise UserError(_("Unknown package."))
        lines = self.move_line_ids.filtered(
            lambda l: l.picked and l.package_id == package)
        if not lines:
            raise UserError(_(
                "Package %(pkg)s is not applied to this transfer.",
                pkg=package.name))
        lines.unlink()
        return True
