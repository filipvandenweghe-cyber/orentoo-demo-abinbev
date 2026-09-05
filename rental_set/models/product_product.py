from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # The set component listing is no longer appended to the sale
    # description.  Standard Odoo logic applies: the quotation line
    # uses the description_sale defined on the product's Sales tab.

    def _rental_physical_total(self, warehouse=False, company=False):
        """Real units this warehouse owns right now — warehouse-local:

            on-hand across the warehouse's OWN internal/transit locations
            + units currently out at a customer that were shipped FROM this
              warehouse (attributed by the order's warehouse).

        The at-customer part is attributed per warehouse instead of counting
        the company-wide rental location, so a company running SEVERAL
        warehouses never sees another warehouse's rented-out stock as
        available here.  For a company with a single warehouse the two are
        identical, so single-warehouse tenants are unaffected.

        Order-independent, canonical implementation.  ``sale.order.line``,
        the rental-set component check and the multi-channel rental flow all
        funnel through this so "total physical stock" has ONE definition.

        The total is conserved and stable across the pick/pack/ship steps
        (a pickup just moves a unit from the warehouse to the at-customer
        location) and multi-step-safe: the at-customer part is measured from
        DONE moves that actually reached the rental location — never the
        intermediate pick/pack legs (see ``_rental_at_customer_qty``).

        :param warehouse: stock.warehouse to scope stock/attribution to
        :param company: res.company owning the rental ("at customer")
            location; when falsy the at-customer part is 0 (callers that want
            it must pass the company explicitly, e.g. the order's)
        """
        self.ensure_one()
        return self._rental_warehouse_onhand(warehouse) \
            + self._rental_at_customer_qty(warehouse, company)

    def _rental_warehouse_onhand(self, warehouse):
        """Current on-hand across the warehouse's OWN internal/transit
        locations only — excludes the company-wide at-customer location, so
        stock never leaks between warehouses of one company.  In a multi-step
        warehouse the pick/pack/output zones are internal children of the
        warehouse view, so units in transit are still counted here (and only
        here).  Falls back to ``qty_available`` when no warehouse is given.
        """
        self.ensure_one()
        if not (warehouse and warehouse.view_location_id):
            return self.qty_available
        locs = self.env['stock.location'].search([
            ('id', 'child_of', warehouse.view_location_id.id),
            ('usage', 'in', ('internal', 'transit')),
        ])
        if not locs:
            return self.qty_available
        total = 0.0
        for dummy_loc, qty in self.env['stock.quant']._read_group(
            [('product_id', '=', self.id), ('location_id', 'in', locs.ids)],
            ['location_id'], ['quantity:sum'],
        ):
            total += qty
        return total

    def _rental_at_customer_qty(self, warehouse, company):
        """Units of this product currently out at a customer that were
        shipped FROM ``warehouse`` — i.e. that reached the rental
        ("at customer") location through an order placed on this warehouse.

        Measured from DONE stock moves, which makes it:

        * multi-step-safe — filtering on ``location_dest_id == rental_loc``
          matches only the final customer-facing leg; the intermediate
          pick/pack legs target internal locations and are ignored, so a unit
          in transit is counted once (by ``_rental_warehouse_onhand``) and
          never double-counted here;
        * setting-agnostic — with Rental Transfers OFF no such moves exist,
          so this is 0 and the base collapses to warehouse on-hand;
        * attributed by ``order.warehouse_id`` — the SAME key
          ``_get_unavailable_qty`` uses for reservations, so the base and the
          reservation term always agree.

        net = Σ done moves INTO rental_loc − Σ done moves OUT of rental_loc,
        for moves whose order is on this warehouse.
        """
        self.ensure_one()
        rental_loc = company.rental_loc_id if company else False
        if not (rental_loc and warehouse):
            return 0.0
        Move = self.env['stock.move']
        base = [
            ('product_id', '=', self.id),
            ('state', '=', 'done'),
            ('sale_line_id.order_id.warehouse_id', '=', warehouse.id),
        ]

        def _summed(extra):
            rows = Move._read_group(base + extra, [], ['quantity:sum'])
            return (rows[0][0] or 0.0) if rows else 0.0

        delivered = _summed([('location_dest_id', '=', rental_loc.id)])
        returned = _summed([('location_id', '=', rental_loc.id)])
        return delivered - returned

    def _rental_available_qty(self, from_date, to_date=False, warehouse=False,
                              ignored_soline_id=False, company=False):
        """Canonical rental availability for a period:

            Available = max(Total physical stock
                            - reserved by OTHER orders (period-aware)
                            - in repair, 0)

        This is the SINGLE definition of "how many additional units of this
        product can be rented for ``[from_date, to_date]``".  It is shared by
        the rental order lines (``sale.order.line._compute_forecast_availability``
        / ``_get_component_available_qty``) and the multi-channel rental flow
        (kiosk / website / POS via ``mcrf_service``), so operational
        availability and any downstream check always agree.

        **Total physical stock** is the conserved quantity the warehouse owns
        right now (on-hand in its own locations + units still out at a customer
        that shipped from it).  It is stable across the pick/pack/ship steps, so
        multi-step staging never inflates availability.

        **Reserved by others** follows the warehouse's real **operations**, not
        the order's declared dates: a rental commits its units from its first
        outbound (pickup) date until its first **inbound (return) operation**
        date.  So a unit still out at a customer whose return operation is
        scheduled *after* the requested window stays reserved — even when the
        order's declared ``return_date`` has already passed (see the regression
        test / order S00338, where the return receipt is scheduled 09-11 while
        the order says 09-05).  This is what native Odoo Rental's warehouse
        forecast expresses via the pickings' move dates; here we express the
        same thing over the conserved total via ``_get_unavailable_qty``, whose
        return timing is grounded on the operation (see
        ``sale.order.line._rental_effective_return_date`` /
        ``_get_active_rental_lines`` / ``_get_rented_quantities``).

        :param from_date: start of the rental period (Datetime)
        :param to_date: end of the rental period (Datetime); defaults to
            ``from_date`` (a single instant)
        :param warehouse: stock.warehouse to scope stock/reservations to
        :param ignored_soline_id: sale.order.line to exclude so an order
            never subtracts its own units from itself; ``False`` counts
            every order (the right choice for a fresh availability question)
        :param company: res.company owning the rental location; defaults to
            the warehouse company, then the current company
        """
        self.ensure_one()
        to_date = to_date or from_date
        if not company:
            company = (warehouse.company_id if warehouse else False) \
                or self.env.company
        wh_id = warehouse.id if warehouse else False

        total = self._rental_physical_total(warehouse=warehouse, company=company)

        reserved_other = 0.0
        if self.rent_ok and hasattr(self, '_get_unavailable_qty'):
            reserved_other = self._get_unavailable_qty(
                from_date, to_date,
                ignored_soline_id=ignored_soline_id, warehouse_id=wh_id,
            )

        in_repair = self._get_repair_unavailable_qty(
            from_date, to_date, warehouse_id=wh_id,
        )
        # Ground confirmed (not-yet-done) interwarehouse / intercompany
        # transfers on their scheduled operation dates.  A relocation OUT of
        # this warehouse reduces it from the departure operation; a relocation
        # IN raises it once the units are guaranteed present for the whole
        # interval.  Both follow the real stock moves (route-based resupply or
        # a manual internal transfer alike), never the order's headers.
        transfer_out = self._get_transfer_out_qty(
            from_date, to_date, warehouse=warehouse,
        )
        transfer_in = self._get_transfer_in_qty(
            from_date, to_date, warehouse=warehouse,
        )
        return max(
            total - reserved_other - in_repair - transfer_out + transfer_in,
            0.0,
        )

    def _get_active_rental_lines(self, from_date, to_date,
                                 ignored_soline_id=False, warehouse_id=False,
                                 **kwargs):
        """Extend native to also catch rentals whose committed interval
        overlaps ``[from_date, to_date]`` when measured by the warehouse's real
        **operations** rather than the order's declared dates.

        Native ``_get_active_rental_lines`` keys on the declared
        ``reservation_begin`` / ``return_date``, so it drops two symmetric
        cases:

        * a unit still physically OUT whose **return operation** is scheduled
          after ``from_date`` even though the declared ``return_date`` is
          earlier — the return receipt was rescheduled (real case S00338);
        * a unit whose **pickup operation** is scheduled before ``to_date``
          even though the declared ``reservation_begin`` is later — the
          delivery picking is scheduled 09-07 for a rental that only starts
          09-08 (real case S00708).

        Both are units the warehouse has really committed over the window, so
        they must keep counting as reserved.  We add back any confirmed rental
        line whose effective interval ``[eff_pickup, eff_return]`` overlaps the
        window and let ``_get_rented_quantities`` place the +/- on the
        operation dates (see ``sale.order.line._rental_effective_pickup_date``
        / ``_rental_effective_return_date``).
        """
        lines = super()._get_active_rental_lines(
            from_date, to_date, ignored_soline_id=ignored_soline_id,
            warehouse_id=warehouse_id, **kwargs)
        to_date = to_date or from_date
        domain = [
            ('is_rental', '=', True),
            ('product_id', '=', self.id),
            ('state', '=', 'sale'),
        ]
        if ignored_soline_id:
            domain.append(('id', '!=', ignored_soline_id))
        if warehouse_id:
            domain.append(('order_id.warehouse_id', '=', warehouse_id))
        candidates = self.env['sale.order.line'].search(domain) - lines

        def _overlaps(line):
            eff_pickup = line._rental_effective_pickup_date() \
                or line.reservation_begin
            eff_return = line._rental_effective_return_date() \
                or line.return_date
            if not eff_pickup or not eff_return:
                return False
            return eff_return > from_date and eff_pickup <= to_date

        return lines | candidates.filtered(_overlaps)

    def _get_repair_unavailable_qty(self, from_date, to_date=False,
                                    warehouse_id=False, lot_id=False):
        """Quantity of this product tied up in **open** repairs whose window
        overlaps ``[from_date, to_date]``.

        A unit under repair is physically present but **not rentable**, and
        standard Odoo does not deduct it from availability (the repair stock
        move is only created at ``action_repair_done``).  We therefore expose
        an explicit, period-aware deduction.

        The ``repair`` module is an **optional** dependency: if it is not
        installed this returns ``0.0`` and never raises.

        :param from_date: start of the rental period (Datetime)
        :param to_date: end of the rental period (Datetime); defaults to from_date
        :param warehouse_id: restrict to repairs located inside this warehouse
        :param lot_id: restrict to a specific serial/lot
        """
        self.ensure_one()
        # Optional dependency — soft check, never import repair directly.
        if 'repair.order' not in self.env:
            return 0.0
        if not from_date:
            return 0.0
        to_date = to_date or from_date

        domain = [
            ('product_id', '=', self.id),
            ('state', 'not in', ('done', 'cancel')),
        ]
        if lot_id:
            domain.append(('lot_id', '=', lot_id))
        if warehouse_id:
            wh = self.env['stock.warehouse'].browse(warehouse_id)
            if wh.view_location_id:
                domain.append(
                    ('location_id', 'child_of', wh.view_location_id.id)
                )
        repairs = self.env['repair.order'].sudo().search(domain)

        now = fields.Datetime.now()
        total = 0.0
        for repair in repairs:
            # Window the unit is unavailable: from creation until the
            # scheduled repair date — but an overdue repair still holds the
            # unit, so extend to "now" when the schedule date is in the past.
            start = repair.create_date or from_date
            end = repair.schedule_date or start
            if end < now:
                end = now
            # Overlap with the requested rental period.
            if start <= to_date and end >= from_date:
                total += repair.product_qty or 0.0
        return total

    def _get_transfer_out_qty(self, from_date, to_date=False, warehouse=False):
        """Units committed to LEAVE this warehouse before/within the window via
        a confirmed (not-yet-done) relocation to another warehouse/company —
        grounded on the transfer move's scheduled date.

        A relocation is any stock move that crosses this warehouse's view-tree
        boundary into another INTERNAL/TRANSIT location (same-company
        interwarehouse, or — through a transit location — intercompany).  It is
        deducted when it departs at or before ``to_date``: a unit leaving at
        any point inside the window is not available for the COMPLETE interval
        (worst case at the end of the window).

        The units are still physically on-hand right now (the move is not done,
        so the conserved physical total still counts them here); this term is
        what makes availability follow the scheduled OUTBOUND operation instead
        of waiting for the move to complete.  It is move-based, so it fires the
        same for a route-driven resupply and a manual internal transfer.

        Excludes:
        * done/cancelled moves — already reflected in the physical total;
        * moves whose destination stays INSIDE this warehouse — internal
          staging, not a departure;
        * moves to a customer / supplier location — sales and vendor returns,
          not relocations of owned stock;
        * moves touching a rental (at-customer) location — rental pickups are
          handled by the reserved term.  The exclusion is by LOCATION (not by
          ``sale_line.is_rental``), so a resupply transfer that merely FEEDS a
          rental still counts as the relocation it is.
        """
        return self._rental_transfer_qty(
            from_date, to_date, warehouse, direction='out')

    def _get_transfer_in_qty(self, from_date, to_date=False, warehouse=False):
        """Units scheduled to ARRIVE into this warehouse via a confirmed
        (not-yet-done) relocation from another warehouse/company — grounded on
        the transfer move's scheduled date.

        Credited only when the arrival is at or before ``from_date``: a unit
        must be present for the WHOLE interval to be rentable for the complete
        column, so an arrival mid-window does not yet raise the operational
        figure (conservative).

        What actually counts is governed per operation type by
        ``stock.picking.type.rental_incoming_policy``:

        * **relocations of OWNED stock** (source internal/transit — an
          interwarehouse / intercompany transfer) count operationally by
          default, because the group already owns the units; set the type to
          ``ignore`` to opt out;
        * **external / produced supply** (a Purchase Order from a supplier, a
          Manufacturing Order, intercompany supply) counts **only** when its
          operation type is set to ``operational`` — the safe default keeps
          uncertain incoming supply out of the booking gate.
        """
        return self._rental_transfer_qty(
            from_date, to_date, warehouse, direction='in')

    def _rental_transfer_qty(self, from_date, to_date, warehouse, direction):
        """Shared engine for the transfer OUT / IN terms.  ``direction`` is
        ``'out'`` (relocations leaving this warehouse, dated by ``to_date``) or
        ``'in'`` (relocations arriving, dated by ``from_date``)."""
        self.ensure_one()
        if not (warehouse and warehouse.view_location_id) or not from_date:
            return 0.0
        to_date = to_date or from_date
        inside = self.env['stock.location'].search([
            ('id', 'child_of', warehouse.view_location_id.id),
            ('usage', 'in', ('internal', 'transit')),
        ])
        if not inside:
            return 0.0
        # Rental (at-customer) locations across every company — their moves are
        # rental pickups/returns, handled by the reserved term, never here.
        rental_loc_ids = self.env['res.company'].sudo().search(
            []).rental_loc_id.ids
        Move = self.env['stock.move']
        if direction == 'out':
            # Relocations LEAVING this warehouse toward another internal/transit
            # location, deducted if they depart by the end of the window.  A
            # departure of owned stock always reduces the source (never gated —
            # ignoring it would over-promise units that are leaving).
            moves = Move.search([
                ('product_id', '=', self.id),
                ('state', 'not in', ('done', 'cancel')),
                ('location_id', 'in', inside.ids),
                ('location_dest_id', 'not in', inside.ids),
                ('location_dest_id.usage', 'in', ('internal', 'transit')),
                ('date', '<=', to_date),
            ])
            total = 0.0
            for move in moves:
                if move.location_dest_id.id in rental_loc_ids:
                    continue
                total += move.product_uom_qty
            return total

        # direction == 'in': everything arriving into this warehouse from
        # OUTSIDE, credited if guaranteed present before the window opens.  Its
        # operational contribution depends on the source and the operation
        # type's policy (``stock.picking.type.rental_incoming_policy``):
        #   * a relocation of OWNED stock (source internal/transit) counts
        #     operationally by default — unless its type is set to 'ignore';
        #   * external / produced supply (PO, MO, intercompany) counts only when
        #     its operation type is explicitly set to 'operational'.
        moves = Move.search([
            ('product_id', '=', self.id),
            ('state', 'not in', ('done', 'cancel')),
            ('location_dest_id', 'in', inside.ids),
            ('location_id', 'not in', inside.ids),
            ('date', '<=', from_date),
        ])
        total = 0.0
        for move in moves:
            if move.location_id.id in rental_loc_ids:
                continue  # rental return — reserved term handles it
            policy = move.picking_type_id.rental_incoming_policy or 'projected'
            if policy == 'ignore':
                continue
            is_relocation = move.location_id.usage in ('internal', 'transit')
            if policy == 'operational' or is_relocation:
                total += move.product_uom_qty
        return total
