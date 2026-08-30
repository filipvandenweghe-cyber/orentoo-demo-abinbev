from odoo import api, fields, models


class RentalSerialLog(models.Model):
    """One entry per serial event in the rental cycle.

    Events:
      * delivered    — serial went out on a rental (client, order, and the
                       package it was in + a contents snapshot).
      * returned     — serial came back.
      * repair_start — serial entered Repair.
      * repair_done  — serial left Repair.
    """

    _name = 'rental.serial.log'
    _description = 'Rental Serial Usage Log'
    _order = 'date desc, id desc'

    lot_id = fields.Many2one(
        'stock.lot', string='Serial/Lot', required=True, index=True,
        ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', string='Product',
        related='lot_id.product_id', store=True)
    event_type = fields.Selection([
        ('delivered', 'Delivered'),
        ('returned', 'Returned'),
        ('repair_start', 'Repair started'),
        ('repair_done', 'Repair done'),
    ], string='Event', required=True, index=True)
    date = fields.Datetime(string='Date', required=True,
                           default=fields.Datetime.now, index=True)

    # Rental context (delivered / returned)
    sale_order_id = fields.Many2one('sale.order', string='Sales Order',
                                    index=True)
    partner_id = fields.Many2one('res.partner', string='Client', index=True)
    picking_id = fields.Many2one('stock.picking', string='Transfer')

    # Packaging context (captured at delivery — Option A)
    package_id = fields.Many2one('stock.package', string='Package')
    package_contents = fields.Char(
        string='Package Contents',
        help='Snapshot of what the package held at delivery time.')

    # Repair context
    repair_order_id = fields.Many2one('repair.order', string='Repair Order')

    note = fields.Char(string='Note')

    def name_get(self):
        labels = dict(self._fields['event_type']._description_selection(self.env))
        result = []
        for log in self:
            result.append((log.id, '%s — %s' % (
                labels.get(log.event_type, log.event_type),
                log.lot_id.name or '')))
        return result

    def action_open_transaction(self):
        """Open the underlying transaction for this log entry — the repair
        order for repair events, otherwise the picking, else the order."""
        self.ensure_one()
        if self.repair_order_id:
            model, rec = 'repair.order', self.repair_order_id
        elif self.picking_id:
            model, rec = 'stock.picking', self.picking_id
        elif self.sale_order_id:
            model, rec = 'sale.order', self.sale_order_id
        else:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': model,
            'res_id': rec.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def _rsl_log(self, vals):
        """Create a log entry unless an identical one already exists
        (idempotent against picking re-validation)."""
        domain = [
            ('lot_id', '=', vals['lot_id']),
            ('event_type', '=', vals['event_type']),
        ]
        if vals.get('picking_id'):
            domain.append(('picking_id', '=', vals['picking_id']))
        if vals.get('repair_order_id'):
            domain.append(('repair_order_id', '=', vals['repair_order_id']))
        if self.sudo().search_count(domain):
            return self.browse()
        return self.sudo().create(vals)
