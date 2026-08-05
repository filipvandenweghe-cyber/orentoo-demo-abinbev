{
    'name': 'Multi-Channel Rental Flow',
    'version': '19.0.1.0.0',
    'summary': 'Multi-channel rental, event, add-on ordering and kiosk flow',
    'description': (
        'Provides a multi-channel ordering flow combining rental items, '
        'event tickets, add-ons and services into a unified dossier with '
        'checkout and payment. Supports website, kiosk and backend channels. '
        'Reuses POS/ePOS/IoT printer configuration for kiosk ticket printing.'
    ),
    'author': 'Kooki BV / Pro-Designed.com',
    'website': 'https://www.pro-designed.com',
    'category': 'Sales/Sales',
    'license': 'LGPL-3',

    # ------------------------------------------------------------------
    # Hard dependencies — must be installed
    # ------------------------------------------------------------------
    'depends': [
        # Core sales & stock
        'sale',
        'sale_stock',
        'stock',
        'product',
        # Rental
        'sale_renting',
        'sale_stock_renting',
        # Website & eCommerce
        'website',
        'website_sale',
        'website_sale_renting',
        'website_payment',
        # Payment engine
        'payment',
        # POS — needed for kiosk config, ePOS printer config, categories
        'point_of_sale',
        'pos_self_order',
        # Warehouse opening hours (adds opening_hours field to warehouse)
        'website_sale_collect',
        # Event ticketing
        'event',
        'event_sale',
        # Custom pricing engine
        'rental_coefficient_dynamic_pricing',
    ],

    # ------------------------------------------------------------------
    # Soft / optional dependencies (handled at runtime)
    #
    # pos_iot, iot               — IoT Box printer support
    # rental_set                 — rental set expansion
    # ------------------------------------------------------------------

    'data': [
        # Security
        'security/ir.model.access.csv',

        # Data
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'data/mail_template_data.xml',

        # Reports
        'report/dossier_ticket_report.xml',

        # Views
        'views/product_views.xml',
        'views/rental_flow_profile_views.xml',
        'views/rental_dossier_views.xml',
        'views/sale_order_views.xml',
        'views/templates/kiosk_ticket_lookup.xml',
        'views/templates/kiosk_order.xml',
        'views/templates/website_flow.xml',
        'views/menu.xml',
    ],

    'demo': [
        'data/demo_data.xml',
    ],

    'assets': {},

    'installable': True,
    'application': False,
    'auto_install': False,
}
