from collections import defaultdict

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class StockPicking(models.Model):
    """Prepared-package / set / serial scanning for pickings.

    Central entry point: ``rental_scanning_scan(barcode, allow_split=False)``.

    The scan is reconciled against the picking's OPEN demand — it never
    creates demand-0 overflow lines and never infers a set from a container
    (see docs/rental_scanning_requirements, PPB-01..14).
    """

    _inherit = 'stock.picking'

    # ── helpers ──────────────────────────────────────────────────────────────

    def _rs_precision(self):
        return self.env['decimal.precision'].precision_get(
            'Product Unit of Measure')

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

    def _rs_remaining_for(self, product_id):
        """Remaining open demand for a product (demand minus done qty)."""
        remaining = 0.0
        for move in self._rs_open_moves(product_id):
            remaining += move.product_uom_qty - move.quantity
        return max(remaining, 0.0)

    def _rs_open_demand(self):
        """Return {product_id: remaining_qty} for all open moves."""
        self.ensure_one()
        demand = defaultdict(float)
        for move in self._rs_open_moves():
            demand[move.product_id.id] += move.product_uom_qty - move.quantity
        return {p: q for p, q in demand.items() if q > 0}

    # ── content extraction ───────────────────────────────────────────────────

    def _rs_contents_from_package(self, package):
        """Return [{'product_id', 'qty', 'lot_id'}] from a package's quants."""
        prec = self._rs_precision()
        contents = []
        for quant in package.contained_quant_ids:
            if float_is_zero(quant.quantity, precision_digits=prec) \
                    or quant.quantity < 0:
                continue
            contents.append({
                'product_id': quant.product_id.id,
                'qty': quant.quantity,
                'lot_id': quant.lot_id.id or False,
            })
        return contents

    def _rs_contents_from_set(self, set_product):
        """Return flattened set components as contents (no lots)."""
        result = []
        self.env['product.template']._collect_leaf_components_for_availability(
            set_product.product_tmpl_id, 1.0, result)
        return [
            {'product_id': product.id, 'qty': qty, 'lot_id': False}
            for product, qty in result
        ]

    # ── barcode resolution ───────────────────────────────────────────────────

    def _rs_resolve_barcode(self, barcode):
        """Resolve a scanned barcode.

        Returns a tuple:
          ('package', package, contents)
          ('set',     product, contents)
          ('product', product, contents)   # single loose serial/product
          (False, False, [])               # unknown
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
            # Is this serial currently inside a package? -> behave as a
            # package scan (PPB-13).  Otherwise fall back to standard
            # single-serial behaviour.
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
                      'lot_id': lot.id}])

        # 3) A product barcode -> set (definition-driven) or plain product
        product = Product.search([('barcode', '=', barcode)], limit=1)
        if product:
            if product.is_rental_set:
                return ('set', product, self._rs_contents_from_set(product))
            return ('product', product,
                    [{'product_id': product.id, 'qty': 1.0, 'lot_id': False}])

        return (False, False, [])

    # ── eligibility (PPB-02) ─────────────────────────────────────────────────

    def _rs_check_package_location(self, package):
        """A package is eligible only if it is at (a sublocation of) the
        picking's source location.  Location-less packages are allowed
        (they will be located by their quants / reservation)."""
        self.ensure_one()
        loc = package.location_id
        if not loc:
            return
        source = self.location_id
        if not (loc == source or loc.parent_path
                and source.parent_path
                and loc.parent_path.startswith(source.parent_path)):
            raise UserError(_(
                "Package %(pkg)s is located in %(loc)s, which is not part of "
                "the source location %(src)s of this operation.",
                pkg=package.name, loc=loc.display_name,
                src=source.display_name,
            ))

    # ── reconciliation core ──────────────────────────────────────────────────

    def _rs_validate_fit(self, contents):
        """Validate contents against open demand.

        Returns (not_demanded, overflow) where:
          not_demanded = [product_id, ...]   (products absent from demand)
          overflow     = [(product_id, qty, remaining), ...]
        """
        prec = self._rs_precision()
        per_product = defaultdict(float)
        for c in contents:
            per_product[c['product_id']] += c['qty']

        not_demanded, overflow = [], []
        for product_id, qty in per_product.items():
            remaining = self._rs_remaining_for(product_id)
            if float_compare(remaining, 0.0, precision_digits=prec) <= 0:
                not_demanded.append(product_id)
            elif float_compare(qty, remaining, precision_digits=prec) > 0:
                overflow.append((product_id, qty, remaining))
        return not_demanded, overflow

    def _rs_fill(self, product_id, qty, lot_id, package):
        """Fill up to ``qty`` of a product into its open moves, sourced from
        ``package`` (and ``lot_id`` if tracked).  Reuses empty reserved
        move-lines where possible; never exceeds demand."""
        prec = self._rs_precision()
        MoveLine = self.env['stock.move.line']
        remaining = qty
        for move in self._rs_open_moves(product_id):
            if float_compare(remaining, 0.0, precision_digits=prec) <= 0:
                break
            move_rem = move.product_uom_qty - move.quantity
            if float_compare(move_rem, 0.0, precision_digits=prec) <= 0:
                continue
            take = min(remaining, move_rem)

            # Reuse an existing, still-empty move-line (typically the
            # loose reservation) instead of creating a duplicate.
            reusable = move.move_line_ids.filtered(
                lambda l: float_is_zero(l.quantity, precision_digits=prec)
                and not l.lot_id
                and not l.package_id
            )[:1]
            vals = {
                'quantity': take,
                'picked': True,
                'package_id': package.id if package else False,
            }
            if lot_id:
                vals['lot_id'] = lot_id
            if reusable:
                reusable.write(vals)
            else:
                MoveLine.create({
                    'move_id': move.id,
                    'picking_id': self.id,
                    'product_id': product_id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    **vals,
                })
            move.picked = True
            remaining -= take

    def _rs_apply(self, contents, package=False, allow_split=False):
        """Reconcile ``contents`` against the picking demand.

        Returns a result dict:
          {'status': 'applied'}                       everything consumed
          {'status': 'partial'}                       consumed up to demand (split)
          {'status': 'need_split', 'overflow': [...]} caller must confirm split
        Raises UserError when a product is not demanded by this operation.
        """
        self.ensure_one()
        prec = self._rs_precision()
        not_demanded, overflow = self._rs_validate_fit(contents)

        if not_demanded:
            names = self.env['product.product'].browse(not_demanded).mapped(
                'display_name')
            raise UserError(_(
                "These products are not required by this operation: %(names)s.\n"
                "If extra stock is genuinely needed, add a line manually.",
                names=", ".join(names),
            ))

        if overflow and not allow_split:
            return {'status': 'need_split', 'overflow': overflow}

        # Apply — cap every product at its remaining demand.
        for c in contents:
            remaining = self._rs_remaining_for(c['product_id'])
            if float_compare(remaining, 0.0, precision_digits=prec) <= 0:
                continue
            take = min(c['qty'], remaining)
            if float_is_zero(take, precision_digits=prec):
                continue
            self._rs_fill(c['product_id'], take, c['lot_id'], package)

        return {'status': 'partial' if overflow else 'applied'}

    # ── public entry point ───────────────────────────────────────────────────

    def rental_scanning_scan(self, barcode, allow_split=False):
        """Scan a package / set / serial and reconcile it against demand.

        This is the single server entry point used by both the backend
        action (PPB-11) and the Barcode client.  Returns the ``_rs_apply``
        result dict, plus 'kind' and (for packages) 'package'.
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

        result = self._rs_apply(contents, package=package,
                                allow_split=allow_split)
        result['kind'] = kind
        if package:
            result['package'] = package.id
        return result
