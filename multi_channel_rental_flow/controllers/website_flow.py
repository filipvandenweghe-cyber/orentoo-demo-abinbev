import json
from datetime import date, datetime, timedelta

from odoo import http, _, fields
from odoo.http import request


class MultiChannelRentalWebsite(http.Controller):
    """Website rental flow controller.

    Provides a themed website ordering flow on separate routes
    (/rental-flow). Uses website.layout for theme integration.
    Reuses the same backend services as the kiosk flow.
    Does NOT override /shop or standard eCommerce.
    """

    def _get_website_flow_translations(self):
        """Build translations dict for website flow JS."""
        return {
            # Calendar
            'mon': _('Mon'), 'tue': _('Tue'), 'wed': _('Wed'),
            'thu': _('Thu'), 'fri': _('Fri'), 'sat': _('Sat'), 'sun': _('Sun'),
            'selected': _('Selected: '),
            # Slots
            'loading': _('Loading...'),
            'no_slots': _('No slots available.'),
            'no_slots_date': _('No slots available on this date.'),
            'available': _('available'),
            'seats': _('seats'),
            # Availability
            'avail_only': _('Only'),
            'avail_available_for': _('available for the selected timeslot, but'),
            'avail_requested': _('requested.'),
            # Events
            'no_events': _('No events available.'),
            # General
            'error_prefix': _('Error: '),
        }

    # ------------------------------------------------------------------
    # Helper: get or create website profile
    # ------------------------------------------------------------------

    def _get_website_profile(self):
        """Find the active website profile for the current website."""
        website = request.website
        profile = request.env['multi.channel.rental.profile'].sudo().search([
            ('profile_type', '=', 'website'),
            ('website_id', '=', website.id),
            ('active', '=', True),
        ], limit=1)
        return profile

    def _get_session_dossier(self):
        """Get or create the dossier stored in the user session."""
        dossier_id = request.session.get('mcrf_dossier_id')
        if dossier_id:
            dossier = request.env['rental.dossier'].sudo().browse(dossier_id)
            if dossier.exists() and dossier.state == 'draft':
                return dossier
        return None

    def _create_session_dossier(self, profile):
        """Create a new dossier for the website session."""
        partner = request.env.user.partner_id
        if request.env.user._is_public():
            partner = profile.default_partner_id or partner

        dossier = request.env['rental.dossier'].sudo().create({
            'partner_id': partner.id,
            'partner_email': partner.email or '',
            'warehouse_id': profile.warehouse_id.id,
            'pricelist_id': profile.pricelist_id.id if profile.pricelist_id else False,
            'profile_id': profile.id,
            'source': 'website',
            'is_multi_channel': True,
        })
        request.session['mcrf_dossier_id'] = dossier.id
        return dossier

    def _get_or_create_dossier(self, profile):
        """Get existing session dossier or create a new one."""
        dossier = self._get_session_dossier()
        if not dossier:
            dossier = self._create_session_dossier(profile)
        return dossier

    # ------------------------------------------------------------------
    # Main pages (HTTP, themed)
    # ------------------------------------------------------------------

    @http.route(
        ['/rental-flow', '/rental-flow/category/<int:category_id>'],
        type='http', auth='public', website=True,
    )
    def catalog(self, category_id=None, **kw):
        """Product catalog page with categories."""
        profile = self._get_website_profile()
        if not profile:
            return request.not_found()

        products = profile._get_available_products()

        # Categories
        ecom_ids = profile.allowed_ecommerce_category_ids
        if not ecom_ids:
            ecom_ids = products.mapped('product_tmpl_id.public_categ_ids')
        categories = ecom_ids.sorted('sequence')

        # Filter by category
        active_category = None
        if category_id:
            active_category = request.env['product.public.category'].browse(
                category_id,
            )
            products = products.filtered(
                lambda p: category_id in p.product_tmpl_id.public_categ_ids.ids
            )

        dossier = self._get_session_dossier()
        basket_count = len(dossier.item_ids) if dossier else 0

        # Compute display prices (min price incl. tax) per product
        svc = request.env['multi.channel.rental.service'].sudo()
        company = profile.company_id
        currency_rec = (
            profile.pricelist_id.currency_id
            if profile.pricelist_id
            else company.currency_id
        )
        currency_name = currency_rec.name
        partner = profile.default_partner_id or request.env['res.partner'].sudo()

        product_prices = {}
        for p in products:
            min_price = p.lst_price
            has_from = False

            if p.multi_channel_item_role == 'rental' and p.requires_duration:
                # Rental: min price from coefficient table
                options = svc._get_duration_options(profile, p)
                if options:
                    prices = []
                    for opt in options:
                        coeff = opt.get('coefficient')
                        if coeff is not None:
                            prices.append(p.lst_price * coeff)
                        else:
                            prices.append(p.lst_price * opt.get('value', 1))
                    if prices:
                        min_price = min(prices)
                        has_from = True

            elif p.multi_channel_item_role == 'event_ticket':
                # Event: lowest available ticket price
                if 'event.event.ticket' in request.env:
                    tickets = request.env['event.event.ticket'].sudo().search([
                        ('product_id', '=', p.id),
                    ]).filtered(lambda t: t.event_id.event_registrations_open)
                    if tickets:
                        available_prices = [
                            t.price for t in tickets
                            if not t.is_sold_out
                        ]
                        if available_prices:
                            min_price = min(available_prices)
                            has_from = len(available_prices) > 1 or True

            taxes = p.taxes_id.filtered(lambda t: t.company_id == company)
            if taxes:
                tax_res = taxes.compute_all(
                    min_price, currency=currency_rec,
                    quantity=1, product=p, partner=partner,
                )
                display_price = tax_res['total_included']
            else:
                display_price = min_price

            product_prices[p.id] = {
                'price': display_price,
                'has_from': has_from,
            }

        return request.render(
            'multi_channel_rental_flow.website_catalog', {
                'profile': profile,
                'products': products,
                'categories': categories,
                'active_category': active_category,
                'basket_count': basket_count,
                'product_prices': product_prices,
                'currency_name': currency_name,
            },
        )

    @http.route(
        '/rental-flow/product/<int:product_id>',
        type='http', auth='public', website=True,
    )
    def product_detail(self, product_id, **kw):
        """Product detail page with datepicker."""
        profile = self._get_website_profile()
        if not profile:
            return request.not_found()

        product = request.env['product.product'].sudo().browse(product_id)
        if not product.exists():
            return request.not_found()

        dossier = self._get_or_create_dossier(profile)

        # Get printer config for JS (reuse kiosk pattern)
        from odoo.addons.multi_channel_rental_flow.controllers.kiosk import (
            MultiChannelRentalKiosk,
        )
        printer_config = MultiChannelRentalKiosk()._get_printer_config(profile)

        translations = self._get_website_flow_translations()

        return request.render(
            'multi_channel_rental_flow.website_product_detail', {
                'profile': profile,
                'product': product,
                'dossier': dossier,
                'printer_config': json.dumps(printer_config),
                'translations_json': json.dumps(translations),
            },
        )

    @http.route(
        '/rental-flow/basket',
        type='http', auth='public', website=True,
    )
    def basket(self, **kw):
        """Dossier basket page."""
        profile = self._get_website_profile()
        if not profile:
            return request.not_found()

        dossier = self._get_session_dossier()
        if not dossier:
            return request.redirect('/rental-flow')

        # Compute basket with taxes
        items_data = []
        subtotal = tax_total = 0.0
        for item in dossier.item_ids.filtered(lambda i: i.state != 'cancelled'):
            taxes = item.product_id.taxes_id.filtered(
                lambda t: t.company_id == dossier.company_id
            )
            if taxes:
                tax_res = taxes.compute_all(
                    item.price_unit,
                    currency=dossier.currency_id,
                    quantity=item.quantity,
                    product=item.product_id,
                    partner=dossier.partner_id,
                )
                item_tax = tax_res['total_included'] - tax_res['total_excluded']
                item_total = tax_res['total_included']
            else:
                item_tax = 0
                item_total = item.price_subtotal

            subtotal += item.price_subtotal
            tax_total += item_tax
            items_data.append({
                'item': item,
                'total_incl': item_total,
            })

        return request.render(
            'multi_channel_rental_flow.website_basket', {
                'profile': profile,
                'dossier': dossier,
                'items_data': items_data,
                'subtotal': subtotal,
                'tax_total': tax_total,
                'total': subtotal + tax_total,
            },
        )

    @http.route(
        '/rental-flow/checkout',
        type='http', auth='public', website=True,
        methods=['POST'], csrf=True,
    )
    def checkout(self, **kw):
        """Process checkout: prepare + pay + redirect to confirmation."""
        profile = self._get_website_profile()
        dossier = self._get_session_dossier()
        if not profile or not dossier:
            return request.redirect('/rental-flow')

        # Update partner email if provided
        email = kw.get('email', '').strip()
        name = kw.get('name', '').strip()
        if email:
            Partner = request.env['res.partner'].sudo()
            partner = Partner.search([('email', '=ilike', email)], limit=1)
            if not partner:
                partner = Partner.create({
                    'name': name or email,
                    'email': email,
                })
            elif name and not partner.name:
                partner.name = name
            dossier.write({
                'partner_id': partner.id,
                'partner_email': email,
            })

        try:
            dossier.action_prepare_for_payment()
            dossier.action_simulate_demo_payment()
            request.session.pop('mcrf_dossier_id', None)
            return request.redirect(
                f'/rental-flow/confirmation/{dossier.id}'
            )
        except Exception as e:
            return request.render(
                'multi_channel_rental_flow.website_checkout_error', {
                    'profile': profile,
                    'dossier': dossier,
                    'error': str(e),
                },
            )

    @http.route(
        '/rental-flow/confirmation/<int:dossier_id>',
        type='http', auth='public', website=True,
    )
    def confirmation(self, dossier_id, **kw):
        """Confirmation page after successful payment."""
        dossier = request.env['rental.dossier'].sudo().browse(dossier_id)
        if not dossier.exists() or dossier.state not in ('paid', 'done'):
            return request.redirect('/rental-flow')

        return request.render(
            'multi_channel_rental_flow.website_confirmation', {
                'dossier': dossier,
            },
        )

    # ------------------------------------------------------------------
    # JSON API (reuses kiosk endpoints with website context)
    # ------------------------------------------------------------------

    @http.route(
        '/rental-flow/api/durations',
        type='jsonrpc', auth='public', website=True, methods=['POST'],
    )
    def api_durations(self, product_id, **kw):
        profile = self._get_website_profile()
        product = request.env['product.product'].sudo().browse(product_id)
        svc = request.env['multi.channel.rental.service'].sudo()
        return {'durations': svc._get_duration_options(profile, product)}

    @http.route(
        '/rental-flow/api/day-states',
        type='jsonrpc', auth='public', website=True, methods=['POST'],
    )
    def api_day_states(self, product_id, center_date_str,
                       duration_value=None, duration_unit=None,
                       quantity=1, item_role='rental', event_id=None, **kw):
        profile = self._get_website_profile()
        product = request.env['product.product'].sudo().browse(product_id)
        svc = request.env['multi.channel.rental.service'].sudo()
        center = date.fromisoformat(center_date_str)
        days = []
        for offset in range(-17, 18):
            day = center + timedelta(days=offset)
            if day < date.today():
                days.append({
                    'date': day.isoformat(),
                    'day_state': 'closed',
                    'color_code': profile.closed_color or '#6c757d',
                })
                continue
            state = svc._get_day_availability_state(
                profile, product, day,
                quantity=float(quantity),
                duration_value=int(duration_value) if duration_value else None,
                duration_unit=duration_unit,
                item_role=item_role,
                event_id=int(event_id) if event_id else None,
            )
            days.append({
                'date': day.isoformat(),
                'day_state': state['day_state'],
                'color_code': state['color_code'],
                'available_slot_count': state.get('available_slot_count', 0),
            })
        return {'days': days}

    @http.route(
        '/rental-flow/api/slots',
        type='jsonrpc', auth='public', website=True, methods=['POST'],
    )
    def api_slots(self, product_id, date_str, duration_value=None,
                  duration_unit=None, quantity=1, item_role='rental',
                  event_id=None, **kw):
        profile = self._get_website_profile()
        product = request.env['product.product'].sudo().browse(product_id)
        svc = request.env['multi.channel.rental.service'].sudo()
        target_date = date.fromisoformat(date_str)
        slots = svc._get_slot_preview(
            profile, product, target_date,
            quantity=float(quantity),
            duration_value=int(duration_value) if duration_value else None,
            duration_unit=duration_unit,
            item_role=item_role,
            event_id=int(event_id) if event_id else None,
        )
        for s in slots:
            for key in ('start_datetime', 'end_datetime'):
                if key in s and isinstance(s[key], datetime):
                    s[key] = s[key].isoformat()
        return {'slots': slots}

    @http.route(
        '/rental-flow/api/events',
        type='jsonrpc', auth='public', website=True, methods=['POST'],
    )
    def api_events(self, product_id, **kw):
        if 'event.event' not in request.env:
            return {'events': []}
        profile = self._get_website_profile()
        company = profile.company_id if profile else request.env.company
        currency = (
            profile.pricelist_id.currency_id
            if profile and profile.pricelist_id
            else company.currency_id
        )
        product = request.env['product.product'].sudo().browse(product_id)
        tickets = request.env['event.event.ticket'].sudo().search([
            ('product_id', '=', product.id),
        ])
        events = []
        for ticket in tickets:
            ev = ticket.event_id
            if not ev.event_registrations_open:
                continue
            # Compute price incl. tax
            price = ticket.price
            taxes = product.taxes_id.filtered(lambda t: t.company_id == company)
            if taxes:
                tax_res = taxes.compute_all(
                    price, currency=currency, quantity=1,
                    product=product,
                )
                price_incl = tax_res['total_included']
            else:
                price_incl = price
            events.append({
                'event_id': ev.id, 'event_name': ev.name,
                'ticket_id': ticket.id, 'ticket_name': ticket.name,
                'price': price_incl,
                'price_excl': price,
                'date_begin': ev.date_begin.isoformat() if ev.date_begin else '',
            })
        return {'events': events}

    @http.route(
        '/rental-flow/api/add-to-basket',
        type='jsonrpc', auth='public', website=True, methods=['POST'],
    )
    def api_add_to_basket(self, product_id, item_role='rental',
                          quantity=1, start_datetime=None,
                          end_datetime=None, price_unit=0,
                          event_id=None, event_ticket_id=None,
                          event_slot_id=None, **kw):
        profile = self._get_website_profile()
        dossier = self._get_or_create_dossier(profile)
        product = request.env['product.product'].sudo().browse(product_id)

        slot = False
        if start_datetime and end_datetime and item_role == 'rental':
            slot = request.env['rental.dossier.slot'].sudo().create({
                'dossier_id': dossier.id,
                'start_datetime': datetime.fromisoformat(start_datetime),
                'end_datetime': datetime.fromisoformat(end_datetime),
                'warehouse_id': dossier.warehouse_id.id,
            })

        item_vals = {
            'dossier_id': dossier.id,
            'slot_id': slot.id if slot else False,
            'product_id': product.id,
            'item_role': item_role,
            'quantity': float(quantity),
            'price_unit': float(price_unit),
        }
        if event_id:
            item_vals['event_id'] = int(event_id)
        if event_ticket_id:
            item_vals['event_ticket_id'] = int(event_ticket_id)
        if event_slot_id:
            item_vals['event_slot_id'] = int(event_slot_id)

        request.env['rental.dossier.item'].sudo().create(item_vals)
        count = len(dossier.item_ids.filtered(lambda i: i.state != 'cancelled'))
        return {'ok': True, 'basket_count': count}

    @http.route(
        '/rental-flow/api/remove-from-basket',
        type='jsonrpc', auth='public', website=True, methods=['POST'],
    )
    def api_remove_from_basket(self, item_id, **kw):
        item = request.env['rental.dossier.item'].sudo().browse(int(item_id))
        dossier = self._get_session_dossier()
        if item.exists() and dossier and item.dossier_id.id == dossier.id:
            slot = item.slot_id
            item.unlink()
            if slot and not slot.item_ids:
                slot.unlink()
        return {'ok': True}

    @http.route(
        '/rental-flow/api/update-qty',
        type='jsonrpc', auth='public', website=True, methods=['POST'],
    )
    def api_update_qty(self, item_id, quantity, **kw):
        item = request.env['rental.dossier.item'].sudo().browse(int(item_id))
        dossier = self._get_session_dossier()
        if not item.exists() or not dossier or item.dossier_id.id != dossier.id:
            return {'ok': False}
        qty = float(quantity)
        if qty <= 0:
            slot = item.slot_id
            item.unlink()
            if slot and not slot.item_ids:
                slot.unlink()
        else:
            item.write({'quantity': qty})
        return {'ok': True}
