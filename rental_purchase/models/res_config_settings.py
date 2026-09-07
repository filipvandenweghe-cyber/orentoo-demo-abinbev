# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rental_purchase_expense_account_id = fields.Many2one(
        related='company_id.rental_purchase_expense_account_id',
        readonly=False,
        string="Rental Purchase Expense Account",
    )
