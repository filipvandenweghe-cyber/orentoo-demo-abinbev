from odoo import fields, models


class ProductTemplate(models.Model):
    """Extend product.template with pricing config and helper methods.

    [RP04, RP05, RP06, RP07]
    """

    _inherit = 'product.template'

    rental_pricing_config_ids = fields.One2many(
        'rental.product.warehouse.pricing.config',
        'product_tmpl_id',
        string='Warehouse Pricing Configuration',
    )

    # -------------------------------------------------------------------------
    # Pricing resolution helpers  [RP05, RP06, RP07]
    #
    # These methods currently return product-level configuration only.
    # They are designed so that product-category fallback can be added in a
    # future version by extending or overriding these methods without
    # rewriting the pricing engine.
    #
    # Intended future resolution order:
    #   1. Product-specific configuration for the warehouse
    #   2. Product-category configuration for the warehouse  (future)
    #   3. Standard / default fallback
    # -------------------------------------------------------------------------

    def _get_applicable_pricing_config(self, warehouse):
        """Return the pricing config record for this product + warehouse.

        :param stock.warehouse warehouse: the sale order warehouse.
        :returns: ``rental.product.warehouse.pricing.config`` recordset
                  (singleton or empty).
        """
        self.ensure_one()
        if not warehouse:
            return self.env['rental.product.warehouse.pricing.config']
        return self.rental_pricing_config_ids.filtered(
            lambda c: c.warehouse_id == warehouse
        )[:1]

    def _get_applicable_dynamic_pricing_table(self, warehouse):
        """Return the dynamic pricing table for this product + warehouse.

        :param stock.warehouse warehouse: the sale order warehouse.
        :returns: ``rental.dynamic.pricing.table`` recordset
                  (singleton or empty).
        """
        self.ensure_one()
        config = self._get_applicable_pricing_config(warehouse)
        return config.dynamic_pricing_table_id if config else \
            self.env['rental.dynamic.pricing.table']

    def _get_applicable_coefficient_tables(self, warehouse):
        """Return the coefficient tables for this product + warehouse.

        :param stock.warehouse warehouse: the sale order warehouse.
        :returns: ``rental.coefficient.table`` recordset (may be empty).
        """
        self.ensure_one()
        config = self._get_applicable_pricing_config(warehouse)
        return config.coefficient_table_ids if config else \
            self.env['rental.coefficient.table']
