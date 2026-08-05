import logging

from odoo import api, models, _

_logger = logging.getLogger(__name__)

# Business requirements: TK01–TK15
# See __init__.py for full index.


class TicketService(models.AbstractModel):
    """Ticket payload generation, lookup and print tracking.

    Provides backend services for kiosk ticket retrieval, PDF report
    generation and print-count tracking. Printer configuration is
    reused from POS/ePOS/IoT via the profile's pos_printer_id.
    """

    _name = 'multi.channel.rental.ticket.service'
    _description = 'Dossier Ticket Service'

    # =================================================================
    # Lookup  [TK01–TK03]
    # =================================================================

    @api.model
    def _find_dossier_for_print_lookup(self, identifier, email):
        """Find a paid dossier by number or order number + email.

        :param str identifier: dossier name (RDxxxxx) or order name (Sxxxxx)
        :param str email: customer email address
        :returns: dict with ok, dossier, message
        """
        if not identifier or not email:
            return {
                'ok': False,
                'dossier': None,
                'message': _("Dossier/order number and email are required."),
            }

        email = email.strip().lower()
        Dossier = self.env['rental.dossier']

        # Try dossier number
        dossier = Dossier.search([
            ('name', '=ilike', identifier.strip()),
            ('state', 'in', ('paid', 'done')),
            '|',
            ('partner_email', '=ilike', email),
            ('partner_id.email', '=ilike', email),
        ], limit=1)

        if dossier:
            return {'ok': True, 'dossier': dossier, 'message': ''}

        # Try order number → find dossier through M2M
        order = self.env['sale.order'].search([
            ('name', '=ilike', identifier.strip()),
            '|',
            ('partner_id.email', '=ilike', email),
            ('partner_id.email', '=ilike', email),
        ], limit=1)
        if order:
            dossier = Dossier.search([
                ('sale_order_ids', 'in', order.id),
                ('state', 'in', ('paid', 'done')),
                '|',
                ('partner_email', '=ilike', email),
                ('partner_id.email', '=ilike', email),
            ], limit=1)
            if dossier:
                return {'ok': True, 'dossier': dossier, 'message': ''}

        return {
            'ok': False,
            'dossier': None,
            'message': _("No paid dossier found for this number and email."),
        }

    # =================================================================
    # Print payload  [TK04–TK08]
    # =================================================================

    @api.model
    def _get_print_payload_for_dossier(self, dossier):
        """Build the full printable ticket payload for a dossier.

        Only returns tickets for paid dossiers.
        """
        dossier.ensure_one()

        if dossier.state not in ('paid', 'done'):
            return {
                'ok': False,
                'message': _("Dossier is not paid."),
                'dossier_name': dossier.name,
                'tickets': [],
            }

        tickets = self._get_ticket_lines_for_dossier(dossier)

        # Get actual totals from confirmed orders (incl. taxes)
        orders = dossier.sale_order_ids.filtered(
            lambda o: o.state != 'cancel'
        )
        amount_untaxed = sum(orders.mapped('amount_untaxed'))
        amount_tax = sum(orders.mapped('amount_tax'))
        amount_total = sum(orders.mapped('amount_total'))

        # Build per-tax summary (like a POS receipt)
        tax_lines = []
        tax_map = {}
        for order in orders:
            for line in order.order_line:
                for tax in line.tax_ids:
                    key = tax.id
                    if key not in tax_map:
                        tax_map[key] = {
                            'name': tax.name,
                            'rate': tax.amount,
                            'base': 0.0,
                            'amount': 0.0,
                        }
                    tax_map[key]['base'] += line.price_subtotal
                    tax_map[key]['amount'] += line.price_tax
        tax_lines = list(tax_map.values())

        return {
            'ok': True,
            'message': '',
            'dossier_name': dossier.name,
            'dossier_description': dossier.description or '',
            'customer': dossier.partner_id.name or '',
            'email': dossier.partner_email or dossier.partner_id.email or '',
            'payment_state': dossier.state,
            'payment_reference': dossier.payment_reference or '',
            'source': dossier.source,
            'amount_untaxed': amount_untaxed or dossier.amount_total,
            'amount_tax': amount_tax,
            'amount_total': amount_total or dossier.amount_total,
            'tax_lines': tax_lines,
            'currency': dossier.currency_id.name,
            'tickets': tickets,
            'ticket_count': len(tickets),
        }

    @api.model
    def _get_ticket_lines_for_dossier(self, dossier):
        """Build individual ticket entries for all printable items.

        - Non-event order lines: one ticket per line per timeslot.
        - Event registrations: one ticket per registration.
        """
        tickets = []
        seq = 0

        for order in dossier.sale_order_ids.filtered(
            lambda o: o.state != 'cancel'
        ):
            # Event registrations
            event_regs = self.env['event.registration'].search([
                ('sale_order_id', '=', order.id),
                ('mcrf_dossier_id', '=', dossier.id),
                ('state', '!=', 'cancel'),
            ]) if 'event.registration' in self.env else self.env['event.registration']

            event_line_ids = set(event_regs.mapped('sale_order_line_id').ids)

            for reg in event_regs:
                seq += 1
                tickets.append(
                    self._build_event_ticket(dossier, order, reg, seq)
                )

            # Non-event order lines
            for line in order.order_line.filtered(
                lambda l: l.id not in event_line_ids
                and l.product_uom_qty > 0
                and not l.display_type
            ):
                seq += 1
                tickets.append(
                    self._build_order_line_ticket(dossier, order, line, seq)
                )

        return tickets

    @api.model
    def _build_event_ticket(self, dossier, order, registration, seq):
        """Build a ticket dict for an event registration."""
        event = registration.event_id
        return {
            'ticket_type': 'event',
            'sequence': seq,
            'dossier_name': dossier.name,
            'order_name': order.name,
            'order_line_ref': (
                registration.sale_order_line_id.display_name
                if registration.sale_order_line_id else ''
            ),
            'product_name': (
                registration.sale_order_line_id.product_id.display_name
                if registration.sale_order_line_id else ''
            ),
            'print_title': event.name if event else _("Event Ticket"),
            'print_subtitle': (
                registration.event_ticket_id.name
                if registration.event_ticket_id else ''
            ),
            'event_name': event.name if event else '',
            'event_date_begin': (
                event.date_begin.isoformat() if event and event.date_begin
                else ''
            ),
            'event_date_end': (
                event.date_end.isoformat() if event and event.date_end
                else ''
            ),
            'event_slot': (
                registration.event_slot_id.display_name
                if registration.event_slot_id else ''
            ),
            'attendee_name': registration.name or '',
            'attendee_email': registration.email or '',
            'registration_barcode': registration.barcode or '',
            'registration_state': registration.state,
            'quantity': 1,
            'price_unit': (
                registration.sale_order_line_id.price_unit
                if registration.sale_order_line_id else 0.0
            ),
            'price_subtotal': (
                registration.sale_order_line_id.price_subtotal /
                max(registration.sale_order_line_id.product_uom_qty, 1)
                if registration.sale_order_line_id else 0.0
            ),
            'timeslot_start': '',
            'timeslot_end': '',
        }

    @api.model
    def _build_order_line_ticket(self, dossier, order, line, seq):
        """Build a ticket dict for a non-event order line."""
        slot = None
        dossier_item = line.mcrf_dossier_item_id
        if dossier_item and dossier_item.slot_id:
            slot = dossier_item.slot_id

        return {
            'ticket_type': 'rental' if line.is_rental else 'product',
            'sequence': seq,
            'dossier_name': dossier.name,
            'order_name': order.name,
            'order_line_ref': line.display_name or '',
            'product_name': line.product_id.display_name,
            'print_title': line.product_id.name,
            'print_subtitle': (
                dossier_item.item_role.replace('_', ' ').title()
                if dossier_item else 'Product'
            ),
            'event_name': '',
            'event_date_begin': '',
            'event_date_end': '',
            'event_slot': '',
            'attendee_name': dossier.partner_id.name or '',
            'attendee_email': (
                dossier.partner_email or dossier.partner_id.email or ''
            ),
            'registration_barcode': '',
            'registration_state': '',
            'quantity': line.product_uom_qty,
            'price_unit': line.price_unit,
            'price_subtotal': line.price_subtotal,
            'price_tax': line.price_tax,
            'price_total': line.price_total,
            'timeslot_start': (
                slot.start_datetime.isoformat() if slot else (
                    order.rental_start_date.isoformat()
                    if order.rental_start_date else ''
                )
            ),
            'timeslot_end': (
                slot.end_datetime.isoformat() if slot else (
                    order.rental_return_date.isoformat()
                    if order.rental_return_date else ''
                )
            ),
        }

    # =================================================================
    # Per-order payload  [TK09]
    # =================================================================

    @api.model
    def _get_print_payload_for_order(self, order):
        """Build ticket payload for a single sale order."""
        dossier = self.env['rental.dossier'].search([
            ('sale_order_ids', 'in', order.id),
            ('state', 'in', ('paid', 'done')),
        ], limit=1)
        if not dossier:
            return {'ok': False, 'message': _("No paid dossier found."), 'tickets': []}

        all_tickets = self._get_ticket_lines_for_dossier(dossier)
        order_tickets = [t for t in all_tickets if t['order_name'] == order.name]
        return {
            'ok': True,
            'message': '',
            'dossier_name': dossier.name,
            'order_name': order.name,
            'tickets': order_tickets,
            'ticket_count': len(order_tickets),
        }

    # =================================================================
    # Per-registration payload  [TK10]
    # =================================================================

    @api.model
    def _get_print_payload_for_event_registration(self, registration):
        """Build ticket payload for a single event registration."""
        dossier_id = registration.mcrf_dossier_id
        order = registration.sale_order_id
        if not dossier_id or dossier_id.state not in ('paid', 'done'):
            return {'ok': False, 'message': _("No paid dossier."), 'tickets': []}

        ticket = self._build_event_ticket(dossier_id, order, registration, 1)
        return {
            'ok': True,
            'message': '',
            'dossier_name': dossier_id.name,
            'tickets': [ticket],
            'ticket_count': 1,
        }

    # =================================================================
    # Print tracking  [TK11]
    # =================================================================

    @api.model
    def _mark_tickets_printed(self, dossier):
        """Mark all generated orders as tickets-printed."""
        generated = self.env['sale.order'].search([
            ('mcrf_dossier_id', '=', dossier.id),
            ('state', '!=', 'cancel'),
        ])
        generated.write({'mcrf_tickets_printed': True})

    @api.model
    def _are_tickets_printed(self, dossier):
        """Check if tickets have already been printed for this dossier."""
        generated = self.env['sale.order'].search([
            ('mcrf_dossier_id', '=', dossier.id),
            ('state', '!=', 'cancel'),
        ])
        if not generated:
            return False
        return all(generated.mapped('mcrf_tickets_printed'))
