# -*- coding: utf-8 -*-
from odoo import models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _compute_account_id(self):
        # Let the standard determination run first, then override only for
        # rental purchase vendor bill lines (§8). Normal bills are untouched.
        super()._compute_account_id()
        for line in self:
            if line.display_type != 'product':
                continue
            po_line = line.purchase_line_id
            if not po_line or not po_line.order_id.is_rental_purchase:
                continue
            if not line.move_id.is_purchase_document(include_receipts=True):
                continue
            account = line._rental_purchase_expense_account()
            if account:
                line.account_id = account

    def _rental_purchase_expense_account(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        account = self.product_id.categ_id.with_company(
            company).rental_purchase_expense_account_id
        if not account:
            account = company.rental_purchase_expense_account_id
        return account
