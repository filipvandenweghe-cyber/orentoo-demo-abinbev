from datetime import date, datetime

from odoo import http
from odoo.http import request

# Business requirements: PR01 (central backend service, no JS duplication)
# See __init__.py for full index.


class MultiChannelRentalAPI(http.Controller):
    """JSON API endpoints for pricing preview, duration options and
    slot availability.

    Used for backend testing and will later serve website/kiosk flows.
    All pricing logic lives in the service layer (PR01).
    """

    @http.route(
        '/multi_channel_rental/api/price_preview',
        type='jsonrpc', auth='user', methods=['POST'],
    )
    def price_preview(self, profile_id, product_id, quantity=1.0,
                      start_datetime=None, end_datetime=None,
                      item_role='rental', partner_id=None, **kw):
        """Return a price preview for a product."""
        svc = request.env['multi.channel.rental.service']
        profile = request.env['multi.channel.rental.profile'].browse(
            profile_id
        )
        product = request.env['product.product'].browse(product_id)
        partner = (
            request.env['res.partner'].browse(partner_id)
            if partner_id else request.env['res.partner']
        )

        start_dt = (
            datetime.fromisoformat(start_datetime)
            if start_datetime else None
        )
        end_dt = (
            datetime.fromisoformat(end_datetime)
            if end_datetime else None
        )

        return svc._get_price_preview(
            profile, product,
            partner=partner,
            quantity=quantity,
            start_dt=start_dt,
            end_dt=end_dt,
            item_role=item_role,
        )

    @http.route(
        '/multi_channel_rental/api/duration_options',
        type='jsonrpc', auth='user', methods=['POST'],
    )
    def duration_options(self, profile_id, product_id,
                         partner_id=None, **kw):
        """Return available duration choices for a product."""
        svc = request.env['multi.channel.rental.service']
        profile = request.env['multi.channel.rental.profile'].browse(
            profile_id
        )
        product = request.env['product.product'].browse(product_id)
        partner = (
            request.env['res.partner'].browse(partner_id)
            if partner_id else request.env['res.partner']
        )
        return svc._get_duration_options(profile, product, partner=partner)

    @http.route(
        '/multi_channel_rental/api/slot_preview',
        type='jsonrpc', auth='user', methods=['POST'],
    )
    def slot_preview(self, profile_id, product_id, date_str,
                     quantity=1.0, duration_value=None,
                     duration_unit=None, item_role='rental',
                     event_id=None, partner_id=None, **kw):
        """Return slots with price previews for a given date."""
        svc = request.env['multi.channel.rental.service']
        profile = request.env['multi.channel.rental.profile'].browse(
            profile_id
        )
        product = request.env['product.product'].browse(product_id)
        partner = (
            request.env['res.partner'].browse(partner_id)
            if partner_id else request.env['res.partner']
        )
        target_date = date.fromisoformat(date_str)

        slots = svc._get_slot_preview(
            profile, product, target_date,
            partner=partner, quantity=quantity,
            duration_value=duration_value,
            duration_unit=duration_unit,
            item_role=item_role, event_id=event_id,
        )

        # Serialize datetimes for JSON
        for s in slots:
            for key in ('start_datetime', 'end_datetime'):
                if key in s and isinstance(s[key], datetime):
                    s[key] = s[key].isoformat()
        return slots

    @http.route(
        '/multi_channel_rental/api/day_availability',
        type='jsonrpc', auth='user', methods=['POST'],
    )
    def day_availability(self, profile_id, product_id, date_str,
                         item_role='rental', event_id=None, **kw):
        """Return availability state for a single day."""
        svc = request.env['multi.channel.rental.service']
        profile = request.env['multi.channel.rental.profile'].browse(
            profile_id
        )
        product = request.env['product.product'].browse(product_id)
        target_date = date.fromisoformat(date_str)
        return svc._get_day_availability_state(
            profile, product, target_date,
            item_role=item_role, event_id=event_id,
        )

    # ------------------------------------------------------------------
    # Ticket lookup & payload  [TK01–TK03]
    # ------------------------------------------------------------------

    @http.route(
        '/multi_channel_rental/api/ticket_lookup',
        type='jsonrpc', auth='public', methods=['POST'],
    )
    def ticket_lookup(self, identifier, email, **kw):
        """Look up a paid dossier by number/order + email and return
        the printable ticket payload."""
        svc = request.env['multi.channel.rental.ticket.service'].sudo()
        result = svc._find_dossier_for_print_lookup(identifier, email)
        if not result['ok']:
            return result

        dossier = result['dossier']
        payload = svc._get_print_payload_for_dossier(dossier)

        # Check if already printed
        payload['already_printed'] = svc._are_tickets_printed(dossier)
        return payload

    @http.route(
        '/multi_channel_rental/api/mark_printed',
        type='jsonrpc', auth='public', methods=['POST'],
    )
    def mark_printed(self, identifier, email, **kw):
        """Mark tickets as printed after kiosk print."""
        svc = request.env['multi.channel.rental.ticket.service'].sudo()
        result = svc._find_dossier_for_print_lookup(identifier, email)
        if not result['ok']:
            return result

        svc._mark_tickets_printed(result['dossier'])
        return {'ok': True, 'message': 'Tickets marked as printed.'}
