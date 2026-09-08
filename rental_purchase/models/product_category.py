# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    # Company-dependent so each company keeps its own rental expense account
    # (§8). Falls back to the company-level account when left empty.
    rental_purchase_expense_account_id = fields.Many2one(
        'account.account',
        company_dependent=True,
        string="Rental Purchase Expense Account",
        domain="[('account_type', 'not in', "
               "('asset_receivable', 'liability_payable', 'asset_cash', "
               "'liability_credit_card', 'off_balance'))]",
        ondelete='restrict',
        help="Expense account used on vendor bill lines that originate from a "
             "Rental Purchase order for products in this category. This is a "
             "rental expense, not an inventory acquisition. Company-specific.",
    )
