{
    'name': 'Rental Scanning',
    'version': '19.0.1.0.0',
    'summary': 'Prepared-package & set picking via scanning (late binding)',
    'description': (
        'Assign a pre-prepared physical package (or a set barcode, or a '
        'packed crate serial) to a picking at pick time and reconcile it '
        'against the operation demand.  Strict-fit with a split prompt on '
        'overflow; works on any operation type; composes with rental sets.\n\n'
        'See docs/rental_scanning_requirements for the full requirements '
        '(PPB-01..14) and rationale.'
    ),
    'author': 'Pro-Designed.com',
    'website': 'https://www.pro-designed.com',
    'category': 'Inventory/Inventory',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'stock_barcode',
        'rental_set',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/rental_scanning_assign_views.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
