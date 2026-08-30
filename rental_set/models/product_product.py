from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # The set component listing is no longer appended to the sale
    # description.  Standard Odoo logic applies: the quotation line
    # uses the description_sale defined on the product's Sales tab.

    def _get_repair_unavailable_qty(self, from_date, to_date=False,
                                    warehouse_id=False, lot_id=False):
        """Quantity of this product tied up in **open** repairs whose window
        overlaps ``[from_date, to_date]``.

        A unit under repair is physically present but **not rentable**, and
        standard Odoo does not deduct it from availability (the repair stock
        move is only created at ``action_repair_done``).  We therefore expose
        an explicit, period-aware deduction.

        The ``repair`` module is an **optional** dependency: if it is not
        installed this returns ``0.0`` and never raises.

        :param from_date: start of the rental period (Datetime)
        :param to_date: end of the rental period (Datetime); defaults to from_date
        :param warehouse_id: restrict to repairs located inside this warehouse
        :param lot_id: restrict to a specific serial/lot
        """
        self.ensure_one()
        # Optional dependency — soft check, never import repair directly.
        if 'repair.order' not in self.env:
            return 0.0
        if not from_date:
            return 0.0
        to_date = to_date or from_date

        domain = [
            ('product_id', '=', self.id),
            ('state', 'not in', ('done', 'cancel')),
        ]
        if lot_id:
            domain.append(('lot_id', '=', lot_id))
        if warehouse_id:
            wh = self.env['stock.warehouse'].browse(warehouse_id)
            if wh.view_location_id:
                domain.append(
                    ('location_id', 'child_of', wh.view_location_id.id)
                )
        repairs = self.env['repair.order'].sudo().search(domain)

        now = fields.Datetime.now()
        total = 0.0
        for repair in repairs:
            # Window the unit is unavailable: from creation until the
            # scheduled repair date — but an overdue repair still holds the
            # unit, so extend to "now" when the schedule date is in the past.
            start = repair.create_date or from_date
            end = repair.schedule_date or start
            if end < now:
                end = now
            # Overlap with the requested rental period.
            if start <= to_date and end >= from_date:
                total += repair.product_qty or 0.0
        return total
