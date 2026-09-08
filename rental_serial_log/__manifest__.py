{
    'name': 'Rental Serial Log',
    'version': '19.0.1.0.6',
    'summary': 'Per-serial rental traceability: delivered / returned / repaired',
    'description': (
        'A persisted usage log per serial-tracked lot.  Records, at rental '
        'delivery validation, which client and sales order the serial was '
        'used for and the package it was in (with a contents snapshot); at '
        'return; and when it enters / leaves Repair.  Surfaced as a Rental '
        'History on the Lot/Serial form.'
    ),
    'author': 'Pro-Designed.com',
    'website': 'https://www.pro-designed.com',
    'category': 'Sales/Rental',
    'license': 'LGPL-3',
    'depends': [
        'sale_stock_renting',  # rental + stock (is_rental_order)
        'repair',              # repair.order
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/rental_serial_log_views.xml',
        'views/stock_lot_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
