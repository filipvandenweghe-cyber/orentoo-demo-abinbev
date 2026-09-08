from odoo import models


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    def write(self, vals):
        res = super().write(vals)
        if 'state' not in vals or self.env.context.get('skip_rental_serial_log'):
            return res
        state = vals['state']
        if state not in ('under_repair', 'done'):
            return res
        Log = self.env['rental.serial.log']
        event = 'repair_start' if state == 'under_repair' else 'repair_done'
        for repair in self:
            lot = repair.lot_id
            if not lot or repair.product_id.tracking != 'serial':
                continue
            note = False
            if state == 'done' and repair.recycle_location_id:
                # A recycle destination hints the unit was scrapped/recycled
                # rather than returned to usable stock.
                note = 'Recycled/scrapped'
            Log._rsl_log({
                'lot_id': lot.id,
                'event_type': event,
                'repair_order_id': repair.id,
                'note': note,
            })
        return res
