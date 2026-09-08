# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Company-level fallback used when the product category has no rental
    # expense account configured (§8).
    rental_purchase_expense_account_id = fields.Many2one(
        'account.account',
        string="Rental Purchase Expense Account",
        domain="[('account_type', 'not in', "
               "('asset_receivable', 'liability_payable', 'asset_cash', "
               "'liability_credit_card', 'off_balance'))]",
        help="Fallback expense account for Rental Purchase vendor bills when "
             "the product category does not define one.",
    )
