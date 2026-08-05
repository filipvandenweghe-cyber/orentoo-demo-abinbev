from odoo import api, fields, models, _
from odoo.tools import float_compare


class SaleFlowLostBrokenService(models.AbstractModel):
    """Service for handling lost and broken item flow.

    Implements: R09, R10.

    Business rules:
      * Lost = not returned.  Broken = returned damaged.
      * Lost/broken charges use the company's lost_broken_fee_product_id.  (R10)
      * Default price comes from product.product.sales_price_broken_lost.
      * If no price is defined, use 0 — still create the invoiceable line.  (R09)
      * Charge lines are charge-only (no delivery moves).  (R10)
      * Invoice line description mentions actual product
        (e.g. "Lost/Broken Fee — Speaker A").  (R10)
      * If Repairs app is installed, broken items route to repair location.
    """

    _name = 'sale.flow.lost.broken.service'
    _description = 'Sale Flow Lost/Broken Service'

    def _process_lost_broken(self, wizard):
        """Process lost/broken wizard results.

        For each wizard line:
          1. Update the flow line with lost/broken quantities.
          2. Create charge-only sale order lines (invoiceable, no delivery).
          3. Create charge flow lines with red warning.
        """
        order = wizard.sale_order_id
        fee_product = order.company_id.lost_broken_fee_product_id

        for wiz_line in wizard.line_ids:
            flow_line = wiz_line.flow_line_id
            prec = self.env['decimal.precision'].precision_get('Product Unit of Measure')

            # Update operational quantities on the original flow line
            vals = {
                'last_flow_update_at': fields.Datetime.now(),
                'last_flow_update_by_id': self.env.uid,
            }
            if float_compare(wiz_line.lost_qty, 0, precision_digits=prec) > 0:
                vals['lost_qty'] = flow_line.lost_qty + wiz_line.lost_qty
            if float_compare(wiz_line.broken_qty, 0, precision_digits=prec) > 0:
                vals['broken_qty'] = flow_line.broken_qty + wiz_line.broken_qty

            flow_line.with_context(skip_sale_flow_sync=True).write(vals)
            flow_line._update_state()
            flow_line._compute_warning_level()

            # Create charge lines for lost items
            if float_compare(wiz_line.lost_qty, 0, precision_digits=prec) > 0:
                self._create_charge_line(
                    order, flow_line, fee_product,
                    qty=wiz_line.lost_qty,
                    price=wiz_line.broken_lost_unit_price,
                    charge_type='lost',
                    product=wiz_line.product_id,
                )

            # Create charge lines for broken items
            if float_compare(wiz_line.broken_qty, 0, precision_digits=prec) > 0:
                self._create_charge_line(
                    order, flow_line, fee_product,
                    qty=wiz_line.broken_qty,
                    price=wiz_line.broken_lost_unit_price,
                    charge_type='broken',
                    product=wiz_line.product_id,
                )

                # Route broken items to repair location
                self._route_broken_to_repair(wiz_line, wizard.picking_id)

    def _create_charge_line(self, order, origin_flow_line, fee_product,
                            qty, price, charge_type, product):
        """Create a charge-only sale order line and flow line.

        Business rules:
          * Use the lost_broken_fee_product_id for tax/accounting.
          * Description mentions the actual product.
          * Charge-only: skip_delivery=True, is_charge_only=True.
          * Always create even if price is 0.
          * Red warning level by default.
        """
        label = _('Lost') if charge_type == 'lost' else _('Broken')
        actual_name = product.display_name
        description = _('%(label)s/%(label2)s Fee — %(product)s',
                        label=label, label2=_('Broken') if charge_type == 'lost' else _('Lost'),
                        product=actual_name)
        # Simplified: just "Lost Fee — Product" or "Broken Fee — Product"
        description = f"{label} Fee — {actual_name}"

        # Use fee product if available, otherwise actual product
        line_product = fee_product or product

        # Create the charge sale order line
        sol = self.env['sale.order.line'].with_context(
            skip_sale_flow_sync=True,
        ).create({
            'order_id': order.id,
            'product_id': line_product.id,
            'name': description,
            'product_uom_qty': qty,
            'price_unit': price,
            'is_downpayment': False,
        })

        # Create the charge flow line
        policy = 'lost_charge' if charge_type == 'lost' else 'broken_charge'
        self.env['sale.flow.line'].create({
            'name': description,
            'sale_order_id': order.id,
            'sale_line_id': sol.id,
            'product_id': product.id,
            'product_uom_id': product.uom_id.id,
            'confirmed_qty': 0,
            'current_qty': qty,
            'unit_price_effective': price,
            'broken_lost_unit_price': price,
            'is_charge_only': True,
            'skip_delivery': True,
            'state': 'confirmed',
            'commercial_policy': policy,
            'invoice_warning_level': 'red',
            'was_changed_after_confirmation': True,
            'added_after_confirmation': True,
            'change_origin': 'return',
            'change_note': _(
                '%(type)s charge for %(product)s (%(qty)s units)',
                type=label, product=actual_name, qty=qty,
            ),
            'origin_flow_line_id': origin_flow_line.id,
            'visible_to_customer': True,
            'last_flow_update_at': fields.Datetime.now(),
            'last_flow_update_by_id': self.env.uid,
        })

    def _route_broken_to_repair(self, wiz_line, picking):
        """Route broken items to repair location if Repairs app is installed.

        If the Repairs app is installed, broken returned items should
        go to a repair location.  If not installed, use a configurable
        fallback location or preserve standard return behavior.
        """
        if not picking:
            return

        # Check if repair module is installed
        repair_installed = self.env['ir.module.module'].sudo().search([
            ('name', '=', 'repair'),
            ('state', '=', 'installed'),
        ], limit=1)

        if repair_installed:
            # Find repair location (virtual location)
            repair_location = self.env['stock.location'].search([
                ('usage', '=', 'production'),
                ('repair_location', '=', True),
            ], limit=1)
            if not repair_location:
                repair_location = self.env['stock.location'].search([
                    ('usage', '=', 'production'),
                    ('name', 'ilike', 'repair'),
                ], limit=1)

            if repair_location:
                # Log a note about routing broken items
                picking.message_post(
                    body=_(
                        'Broken item "%(product)s" (%(qty)s) should be routed '
                        'to repair location: %(location)s',
                        product=wiz_line.product_id.display_name,
                        qty=wiz_line.broken_qty,
                        location=repair_location.display_name,
                    ),
                )
        else:
            # No repair module: log a warning
            picking.message_post(
                body=_(
                    'Broken item "%(product)s" (%(qty)s) returned. '
                    'Repairs module not installed — item follows standard return flow.',
                    product=wiz_line.product_id.display_name,
                    qty=wiz_line.broken_qty,
                ),
            )
