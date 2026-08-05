import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)

# Business requirements: SO07, PY01–PY10
# See __init__.py for full index.


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    mcrf_dossier_id = fields.Many2one(
        'rental.dossier',
        string="Rental Dossier",
        copy=False,
        index=True,
        help="Dossier linked to this payment transaction.",
    )

    def _post_process(self):
        """Override to add dossier-level payment orchestration.

        When a transaction is linked to a dossier, we handle the
        success/failure at the dossier level instead of relying on
        the standard sale module's per-order logic.

        Standard sale order confirmation is already done by
        action_prepare_for_payment(), so we skip the standard
        _check_amount_and_confirm_order() for dossier transactions
        by letting super() run first, then applying dossier logic.
        """
        # Let Odoo's standard sale/payment post-processing run first.
        # For dossier-linked transactions with multiple sale_order_ids,
        # the standard _check_amount_and_confirm_order skips confirmation
        # (only works for single-order transactions), which is fine —
        # our orders are already confirmed by prepare_for_payment.
        super()._post_process()

        # Now handle dossier-level logic
        for tx in self:
            dossier = tx.mcrf_dossier_id
            if not dossier:
                continue

            if tx.state in ('done', 'authorized'):
                try:
                    dossier.action_payment_success(transaction=tx)
                except Exception as e:
                    _logger.warning(
                        "Dossier payment success failed for %s: %s",
                        dossier.name, e,
                    )
                    dossier.write({'state': 'payment_exception'})

            elif tx.state == 'cancel':
                try:
                    dossier.action_payment_failed(transaction=tx)
                except Exception as e:
                    _logger.warning(
                        "Dossier payment failure handling failed for %s: %s",
                        dossier.name, e,
                    )

            elif tx.state == 'error':
                try:
                    dossier.action_payment_failed(transaction=tx)
                except Exception as e:
                    _logger.warning(
                        "Dossier payment error handling failed for %s: %s",
                        dossier.name, e,
                    )
