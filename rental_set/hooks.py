import logging

_logger = logging.getLogger(__name__)


def _enable_rental_pickings(env):
    """Ensure the 'Rental pickings' feature is enabled.

    Availability (``rental_reserved_self`` and the round-trip pickup/return
    transfers this module relies on) is derived from real rental picking
    moves. Those only exist when ``sale_stock_renting.group_rental_stock_picking``
    is active. Fresh build DBs ship with it OFF, so enable it on install the
    same way the Inventory settings toggle does — this also provisions the
    rental (at-customer) location and the warehouse rental rules.
    """
    if env['res.groups']._is_feature_enabled(
            'sale_stock_renting.group_rental_stock_picking'):
        return
    env['res.config.settings'].create(
        {'group_rental_stock_picking': True}).set_values()
    _logger.info("rental_set: enabled 'Rental pickings' feature.")
