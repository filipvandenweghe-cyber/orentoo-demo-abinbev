from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()
        if self.env.context.get('skip_rental_serial_log'):
            return res
        for picking in self:
            # Only after the picking is actually done (super may return a
            # backorder/immediate-transfer wizard before that).
            if picking.state == 'done':
                picking._rental_serial_log_record()
        return res

    def _rental_serial_log_record(self):
        """Log serial delivered/returned events for a rental transfer.

        Delivered is logged only on the customer-facing OUTGOING delivery
        (not on internal Pick/Pack), with the package the serial was in and a
        contents snapshot (Option A).  Returned is logged on the return
        receipt (return_id set).
        """
        self.ensure_one()
        order = self.sale_id
        if not order or not getattr(order, 'is_rental_order', False):
            return
        is_return = bool(self.return_id)
        is_delivery = self.picking_type_code == 'outgoing' and not is_return
        if not (is_return or is_delivery):
            return

        Log = self.env['rental.serial.log']
        for line in self.move_line_ids:
            lot = line.lot_id
            if not lot or line.product_id.tracking != 'serial':
                continue
            if line.quantity <= 0:
                continue
            if is_return:
                Log._rsl_log({
                    'lot_id': lot.id,
                    'event_type': 'returned',
                    'sale_order_id': order.id,
                    'partner_id': order.partner_id.id,
                    'picking_id': self.id,
                })
            else:  # delivery
                pkg = line.package_id or line.result_package_id
                Log._rsl_log({
                    'lot_id': lot.id,
                    'event_type': 'delivered',
                    'sale_order_id': order.id,
                    'partner_id': order.partner_id.id,
                    'picking_id': self.id,
                    'package_id': pkg.id if pkg else False,
                    'package_contents':
                        self._rental_serial_pkg_contents(pkg) if pkg else '',
                })

    def _rental_serial_pkg_contents(self, package):
        """Readable snapshot of what a package held on this transfer."""
        self.ensure_one()
        parts = []
        for line in self.move_line_ids:
            if line.quantity <= 0:
                continue
            if line.package_id != package and line.result_package_id != package:
                continue
            lot = ' [%s]' % line.lot_id.name if line.lot_id else ''
            parts.append('%s× %s%s' % (
                ('%g' % line.quantity), line.product_id.display_name, lot))
        return ', '.join(parts)
