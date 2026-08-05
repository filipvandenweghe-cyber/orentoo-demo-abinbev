import logging

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Business requirements: PP01–PP13
# See __init__.py for full index.


class PaymentPreparationService(models.AbstractModel):
    """Prepare-for-payment orchestration.  [PP01–PP03]

    Validates the dossier, checks availability, generates and confirms
    sale orders, and moves the dossier to payment_pending — all as an
    atomic, all-or-nothing operation.

    Availability strategy:
    - Forecasted stock is used as a SOFT WARNING (displayed on items
      but does not block the flow). Forecasts can be slightly inaccurate.
    - The actual order confirmation (action_confirm) is the HARD GATE.
      Odoo's stock move reservation is the source of truth — it either
      reserves the units or fails. If it fails, we roll back everything.
    - This ensures we never leave rentable stock on the table due to
      forecast inaccuracies.
    """

    _name = 'multi.channel.rental.payment.prep'
    _description = 'Dossier Payment Preparation Service'

    # =================================================================
    # Public API
    # =================================================================

    @api.model
    def _prepare_for_payment(self, dossier):
        """Prepare a dossier for payment: validate, check availability,
        generate orders, confirm them, and set state to payment_pending.

        This is an all-or-nothing operation. If order confirmation fails
        (stock reservation error), all generated orders are rolled back.

        :param rental.dossier dossier: singleton dossier record
        :raises UserError: with a clear message if preparation fails
        """
        dossier.ensure_one()

        if dossier.state in ('paid', 'done'):
            raise UserError(
                _("Dossier %s is already paid or done.", dossier.name)
            )
        if dossier.state == 'cancelled':
            raise UserError(
                _("Dossier %s is cancelled. Reset to draft first.",
                  dossier.name)
            )

        # Idempotency: if already payment_pending with confirmed orders,
        # just return — nothing to do.
        if dossier.state == 'payment_pending':
            generated = self._get_generated_orders(dossier)
            if generated and all(o.state == 'sale' for o in generated):
                return True

        order_svc = self.env['multi.channel.rental.order.service']

        # ----------------------------------------------------------
        # Step 1: Validate dossier data
        # ----------------------------------------------------------
        dossier._validate_for_confirmation()

        # ----------------------------------------------------------
        # Step 2: Generate or update draft orders
        # ----------------------------------------------------------
        generated = order_svc._generate_sale_orders(dossier)
        if not generated:
            generated = self._get_generated_orders(dossier)

        if not generated:
            raise UserError(
                _("No orders to process. Add items or slots first.")
            )

        # ----------------------------------------------------------
        # Step 3: Availability check (BLOCKING for rental items)
        #
        # Uses per-point-in-time virtual_available check across the
        # rental period. This is the accurate availability gate for
        # rental orders (the hard gate on move state is skipped for
        # rentals because Odoo creates future-dated moves in confirmed
        # state by design).
        # ----------------------------------------------------------
        warnings = self._check_availability_soft(dossier)
        blocking_issues = [w for w in warnings if w.startswith('BLOCK:')]
        soft_warnings = [w for w in warnings if not w.startswith('BLOCK:')]

        if blocking_issues:
            self._rollback_generated_orders(dossier, generated)
            msg = _("Insufficient stock:")
            msg += '\n' + '\n'.join(
                w.replace('BLOCK: ', '') for w in blocking_issues
            )
            if soft_warnings:
                msg += '\n\n' + _("Additional warnings:") + '\n'
                msg += '\n'.join(soft_warnings)
            raise UserError(msg)

        if soft_warnings:
            _logger.info(
                "Dossier %s availability warnings: %s",
                dossier.name, '; '.join(soft_warnings),
            )

        # ----------------------------------------------------------
        # Step 4: Confirm all generated orders
        # ----------------------------------------------------------
        try:
            self._confirm_all_orders(generated)
        except Exception as e:
            self._rollback_generated_orders(dossier, generated)
            _logger.warning(
                "Order confirmation failed for dossier %s: %s",
                dossier.name, e,
            )
            msg = _("Could not confirm orders.")
            if warnings:
                msg += '\n\n' + _("Availability warnings:") + '\n'
                msg += '\n'.join(warnings)
            msg += '\n\n' + _("Technical detail: %s", e)
            raise UserError(msg) from e

        # ----------------------------------------------------------
        # Step 5: HARD GATE — verify stock reservation succeeded
        #
        # Odoo's action_confirm does not raise on insufficient stock.
        # Instead it creates partially_available moves. We check the
        # actual move states after confirmation: if any rental pickup
        # move is not fully assigned, stock is truly insufficient.
        # ----------------------------------------------------------
        reservation_issues = self._verify_stock_reservations(
            dossier, generated,
        )
        if reservation_issues:
            self._rollback_generated_orders(dossier, generated)
            msg = _("Insufficient stock — reservation failed:")
            msg += '\n' + '\n'.join(reservation_issues)
            if warnings:
                msg += '\n\n' + _("Forecast warnings:") + '\n'
                msg += '\n'.join(warnings)
            raise UserError(msg)

        # ----------------------------------------------------------
        # Step 6: Update dossier and item states
        # ----------------------------------------------------------
        dossier.item_ids.filtered(
            lambda i: i.state == 'generated'
        ).write({'state': 'confirmed'})

        dossier.slot_ids.filtered(
            lambda s: s.state == 'order_created'
        ).write({'state': 'confirmed'})

        # Mark all confirmed items as available (reservation succeeded)
        dossier.item_ids.filtered(
            lambda i: i.state == 'confirmed'
        ).write({'availability_state': 'available'})

        if dossier.state in ('draft', 'confirmed'):
            dossier.write({'state': 'payment_pending'})

        # Recompute totals from confirmed orders
        dossier.action_recompute_totals()

        return True

    # =================================================================
    # Soft availability check (informational, does not block)
    # =================================================================

    @api.model
    def _check_availability_soft(self, dossier):
        """Check availability for all active dossier items.

        Uses the per-point-in-time availability check for rental items.
        Returns a list of messages:
        - 'BLOCK: ...' for items that must be blocked (insufficient stock)
        - Regular messages for soft warnings

        Also updates item.availability_state for display.
        """
        warnings = []
        mcrf_svc = self.env['multi.channel.rental.service']

        for item in dossier.item_ids.filtered(
            lambda i: i.state not in ('cancelled',)
        ):
            product = item.product_id
            warehouse = (
                (item.slot_id and item.slot_id.warehouse_id)
                or dossier.warehouse_id
            )
            start_dt = item.slot_id.start_datetime if item.slot_id else None
            end_dt = item.slot_id.end_datetime if item.slot_id else None

            if item.item_role == 'rental':
                avail = mcrf_svc._get_forecasted_availability(
                    product, warehouse, start_dt, end_dt,
                    quantity=item.quantity, item_role='rental',
                )
                if avail['availability_state'] == 'unavailable':
                    msg = _(
                        "%(product)s: only %(available)s available, "
                        "%(requested)s requested.",
                        product=product.display_name,
                        available=avail['available_qty'],
                        requested=item.quantity,
                    )
                    # BLOCK rental items — per-point check is accurate
                    warnings.append('BLOCK: ' + msg)
                    item.availability_state = 'unavailable'
                elif avail['availability_state'] == 'available':
                    item.availability_state = 'available'
                else:
                    item.availability_state = 'unknown'

            elif item.item_role == 'event_ticket':
                event_issue = self._check_event_capacity(item)
                if event_issue:
                    # BLOCK event tickets with insufficient capacity
                    warnings.append('BLOCK: ' + event_issue)
                    item.availability_state = 'unavailable'
                else:
                    item.availability_state = 'available'

            else:
                # addons / services — always available
                item.availability_state = 'available'

        return warnings

    @api.model
    def _check_event_capacity(self, item):
        """Check event ticket capacity for a dossier item.

        Returns a warning string or None if available.
        Note: event capacity is also a soft check — the real gate is
        whether event registration creation succeeds.
        """
        if 'event.event' not in self.env or not item.event_id:
            return None

        event = item.event_id
        if not event.exists():
            return _("Event not found for '%s'.", item.product_id.display_name)

        if event.event_registrations_sold_out:
            return _(
                "%(product)s: event '%(event)s' is sold out.",
                product=item.product_id.display_name,
                event=event.name,
            )

        # Check specific event slot capacity (for multi-slot events)
        if item.event_slot_id:
            slot = item.event_slot_id
            if slot.is_sold_out:
                return _(
                    "%(product)s: time slot '%(slot)s' is sold out.",
                    product=item.product_id.display_name,
                    slot=slot.display_name,
                )
            if event.seats_max > 0 and slot.seats_available < item.quantity:
                return _(
                    "%(product)s: only %(available)s seats available "
                    "for '%(slot)s' (%(requested)s requested).",
                    product=item.product_id.display_name,
                    available=slot.seats_available,
                    slot=slot.display_name,
                    requested=int(item.quantity),
                )
        # Check event-level capacity
        elif event.seats_max > 0 and event.seats_available < item.quantity:
            return _(
                "%(product)s: only %(available)s seats available "
                "for '%(event)s' (%(requested)s requested).",
                product=item.product_id.display_name,
                available=event.seats_available,
                event=event.name,
                requested=int(item.quantity),
            )

        return None

    # =================================================================
    # Stock reservation verification (the REAL hard gate)
    # =================================================================

    @api.model
    def _verify_stock_reservations(self, dossier, orders):
        """Verify that all stock moves are fully reserved after
        order confirmation.

        Odoo's action_confirm does not raise on insufficient stock —
        it creates moves in 'partially_available' or 'confirmed' state.
        We check the actual move states to detect real shortages.

        Only checks outgoing (pickup) moves for rental/storable items.
        Return moves and service items are skipped.

        :returns: list of issue strings. Empty = all fully reserved.
        """
        issues = []
        for order in orders:
            # Skip rental orders — Odoo's rental system creates pickup
            # moves in confirmed/partially_available state by design
            # when items are currently out on other rentals but expected
            # back before the pickup date. The scheduler assigns them
            # closer to the actual pickup date. Blocking here would
            # prevent valid future-dated rental bookings.
            if order.is_rental_order:
                continue

            for picking in order.picking_ids:
                # Skip return/incoming pickings — only check pickups
                if picking.picking_type_code == 'incoming':
                    continue
                for move in picking.move_ids:
                    if move.state in ('done', 'cancel', 'assigned'):
                        continue
                    # partially_available or confirmed = shortage
                    product = move.product_id
                    reserved = move.quantity
                    requested = move.product_uom_qty
                    issues.append(_(
                        "%(product)s: only %(reserved)s of %(requested)s "
                        "could be reserved (order %(order)s).",
                        product=product.display_name,
                        reserved=reserved,
                        requested=requested,
                        order=order.name,
                    ))
        return issues

    # =================================================================
    # Order confirmation
    # =================================================================

    @api.model
    def _confirm_all_orders(self, orders):
        """Confirm all generated draft orders.

        This triggers Odoo's stock move reservation which is the
        source of truth for availability. If any order can't be
        fulfilled, the confirmation raises an exception.
        """
        draft_orders = orders.filtered(lambda o: o.state == 'draft')
        if draft_orders:
            draft_orders.action_confirm()

        # Verify all orders are now confirmed
        failed = orders.filtered(lambda o: o.state not in ('sale', 'done'))
        if failed:
            raise UserError(
                _("Failed to confirm orders: %s",
                  ', '.join(failed.mapped('name')))
            )

    # =================================================================
    # Rollback
    # =================================================================

    @api.model
    def _rollback_generated_orders(self, dossier, orders):
        """Cancel/reset generated orders after a failed preparation.

        Only touches orders that were generated by the dossier
        (mcrf_dossier_id is set). Does not touch manually linked orders.
        """
        generated = orders.filtered(
            lambda o: o.mcrf_dossier_id == dossier
        )
        for order in generated:
            try:
                if order.state in ('sale', 'draft'):
                    order.action_cancel()
            except Exception as e:
                _logger.warning(
                    "Could not cancel order %s during rollback: %s",
                    order.name, e,
                )

        # Reset item states back to generated/draft
        dossier.item_ids.filtered(
            lambda i: i.state == 'confirmed'
        ).write({'state': 'generated'})

        dossier.slot_ids.filtered(
            lambda s: s.state == 'confirmed'
        ).write({'state': 'order_created'})

    # =================================================================
    # Helpers
    # =================================================================

    @api.model
    def _get_generated_orders(self, dossier):
        """Return all sale orders generated by the dossier."""
        return self.env['sale.order'].search([
            ('mcrf_dossier_id', '=', dossier.id),
            ('state', '!=', 'cancel'),
        ])
