{
    'name': 'Pro-Designed.com Company Setup',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localizations',
    'author': 'Pro-Designed.com',
    'summary': 'Sets up the Pro-Designed.com Belgian company (EUR, Belgian PCMN chart, VAT, fiscal positions).',
    'description': """
Pro-Designed.com Company Setup
==============================
Creates and configures a Belgian company named **Pro-Designed.com** on install:

* Country: Belgium, VAT: BE0715939182
* Currency: EUR
* Chart of accounts: Belgium - Companies (PCMN)
* Fiscal positions: loaded from the Belgian localization
  (Domestic, Intra-Community, EU B2C, Extra-Community, Co-Contractant, Non Deductible)

The setup runs in an idempotent ``post_init_hook`` so it survives Odoo.sh rebuilds
once this module is committed and installed on the branch.
""",
    'depends': ['l10n_be'],
    'demo': [
        'demo/restore_chart_marker.xml',
    ],
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
