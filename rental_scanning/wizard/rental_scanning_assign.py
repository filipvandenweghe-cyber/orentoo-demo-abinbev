from odoo import _, fields, models


class RentalScanningAssign(models.TransientModel):
    """Backend counterpart of the Barcode scan (PPB-11).

    Type or scan a barcode (package reference, set barcode, or serial);
    it is reconciled against the picking demand with the exact same server
    logic as the Barcode client.  On overflow the user is asked to split.
    """

    _name = 'rental.scanning.assign'
    _description = 'Assign Prepared Package / Set to Picking'

    picking_id = fields.Many2one(
        'stock.picking', string='Transfer', required=True, ondelete='cascade')
    barcode = fields.Char(string='Package / Set / Serial', required=True)
    info = fields.Text(string='Info', readonly=True)
    split_pending = fields.Boolean(readonly=True)

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'rental.scanning.assign',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply(self, allow_split=False):
        self.ensure_one()
        result = self.picking_id.rental_scanning_scan(
            self.barcode, allow_split=allow_split)
        status = result.get('status')
        if status == 'need_split':
            self.write({
                'split_pending': True,
                'info': _(
                    "This package holds more of some products than this "
                    "operation still needs.\n"
                    "Opening (splitting) the package is real work — confirm to "
                    "consume only what is needed and leave the remainder in the "
                    "package, or cancel."),
            })
            return self._reopen()
        # applied / partial -> done
        return {'type': 'ir.actions.act_window_close'}

    def action_confirm_split(self):
        return self.action_apply(allow_split=True)
