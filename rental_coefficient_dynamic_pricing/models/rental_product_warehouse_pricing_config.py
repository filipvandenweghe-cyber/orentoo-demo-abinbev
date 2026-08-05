from odoo import api, fields, models


class RentalProductWarehousePricingConfig(models.Model):
    """Per-product, per-warehouse pricing configuration.  [RP01, RP02, RP03]

    Links a product template to a specific warehouse and defines which
    coefficient tables and dynamic pricing table apply for that combination.
    """

    _name = 'rental.product.warehouse.pricing.config'
    _description = 'Product Warehouse Pricing Configuration'
    _order = 'product_tmpl_id, warehouse_id'

    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product',
        required=True,
        ondelete='cascade',
        index=True,
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='warehouse_id.company_id',
        store=True,
        readonly=True,
    )
    dynamic_pricing_table_id = fields.Many2one(
        'rental.dynamic.pricing.table',
        string='Dynamic Pricing Table',
        ondelete='set null',
        domain="[('company_id', '=', company_id)]",
    )
    coefficient_table_ids = fields.Many2many(
        'rental.coefficient.table',
        relation='rental_pwpc_coeff_table_rel',
        column1='config_id',
        column2='table_id',
        string='Coefficient Tables',
        domain="[('company_id', '=', company_id)]",
    )

    # RP02: unique product + warehouse
    _unique_product_warehouse = models.Constraint(
        'UNIQUE(product_tmpl_id, warehouse_id)',
        'A pricing configuration already exists for this product and warehouse.',
    )
