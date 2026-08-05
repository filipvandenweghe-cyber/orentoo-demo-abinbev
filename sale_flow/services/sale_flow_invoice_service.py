from odoo import api, fields, models, _
from odoo.tools import float_compare


class SaleFlowInvoiceService(models.AbstractModel):
    """Service for invoice preparation using sale.flow.line data.

    Implements: R06, R13.

    Business rules:
      * Draft invoice is initially based on confirmed quantities and prices.
      * Warning levels indicate differences:  (R06)
          - orange: operational change, invoice <= confirmed value
          - red: invoice value exceeds confirmed value
      * The invoicing user may manually adjust quantities.
      * Lines with confirmed_qty=0 are internal by default.
      * Products added during delivery appear on invoice by default.  (R13)
    """

    _name = 'sale.flow.invoice.service'
    _description = 'Sale Flow Invoice Service'

    def _prepare_invoice_data(self, order):
        """Prepare invoice data from flow lines.

        Returns a list of dicts with invoice line information, highlighting
        any differences between confirmed and actual quantities.

        The draft invoice should initially use confirmed quantities/prices.
        Differences are surfaced as warnings, not automatic adjustments.
        """
        result = []
        prec = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        for fl in order.flow_line_ids.filtered(
            lambda f: f.state not in ('cancelled', 'draft')
        ):
            data = {
                'flow_line': fl,
                'product_id': fl.product_id,
                'description': fl.confirmed_description or fl.name,
                'quantity': fl.confirmed_qty,
                'price_unit': fl.confirmed_unit_price,
                'discount': fl.confirmed_discount,
                'warning_level': fl.invoice_warning_level,
                'actual_delivered_qty': fl.delivered_qty,
                'actual_returned_qty': fl.returned_qty,
                'difference_note': False,
            }

            # Highlight differences
            if float_compare(fl.delivered_qty, fl.confirmed_qty, precision_digits=prec) != 0:
                data['difference_note'] = _(
                    'Confirmed: %(conf)s, Delivered: %(dlv)s',
                    conf=fl.confirmed_qty, dlv=fl.delivered_qty,
                )

            # For charge-only lines (lost/broken), use their own qty/price
            if fl.is_charge_only:
                data['quantity'] = fl.current_qty
                data['price_unit'] = fl.unit_price_effective

            # Skip internal-only lines from customer invoice
            if not fl.visible_to_customer and not fl.is_charge_only:
                data['internal_only'] = True

            result.append(data)

        return result

    def _link_invoice_lines(self, flow_line, invoice_lines):
        """Link invoice lines to a flow line and update invoiced qty."""
        flow_line.with_context(skip_sale_flow_sync=True).write({
            'invoice_line_ids': [(4, il.id) for il in invoice_lines],
            'invoiced_qty': sum(invoice_lines.mapped('quantity')),
            'last_flow_update_at': fields.Datetime.now(),
            'last_flow_update_by_id': self.env.uid,
        })
        if flow_line.invoiced_qty >= flow_line.current_qty:
            flow_line.with_context(skip_sale_flow_sync=True).write({
                'state': 'invoiced',
            })
