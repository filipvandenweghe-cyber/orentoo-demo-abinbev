from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_move_lines_to_report(self):
        """Exclude Rental Set component lines from invoice PDF.

        If an invoice line is linked to a hidden set component
        (visible_to_customer=False), it should not appear on the
        customer-facing invoice document.
        """
        lines = super()._get_move_lines_to_report()
        return lines.filtered(
            lambda l: not l.sale_line_ids
            or not any(
                sl.is_set_component and not sl.visible_to_customer
                for sl in l.sale_line_ids
            )
        )
