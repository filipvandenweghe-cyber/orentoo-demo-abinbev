import logging

_logger = logging.getLogger(__name__)

COMPANY_NAME = 'Pro-Designed.com'
COMPANY_VAT = 'BE0715939182'
CHART_TEMPLATE = 'be_comp'  # Belgium - Companies (PCMN)


def post_init_hook(env):
    """Create/configure the Pro-Designed.com Belgian company.

    Idempotent: safe to run again on module update or on a fresh Odoo.sh
    rebuild. It creates the company if missing, loads the Belgian chart of
    accounts (which brings EUR + the Belgian fiscal positions), sets the VAT
    number, and makes the company the default one for the admin user.
    """
    country_be = env.ref('base.be')
    eur = env.ref('base.EUR')
    if not eur.active:
        eur.active = True

    company = env['res.company'].search([('name', '=', COMPANY_NAME)], limit=1)
    if not company:
        company = env['res.company'].create({
            'name': COMPANY_NAME,
            'country_id': country_be.id,
        })
        _logger.info('pro_designed_setup: created company %s (id=%s)', COMPANY_NAME, company.id)
    else:
        _logger.info('pro_designed_setup: reusing existing company %s (id=%s)', COMPANY_NAME, company.id)
        if company.country_id != country_be:
            company.country_id = country_be

    # Load the Belgian chart of accounts if not already loaded.
    # This also sets the company currency to EUR and creates the Belgian
    # fiscal positions (Domestic, Intra-Community, EU B2C, Extra-Community,
    # Co-Contractant, Non Deductible).
    if company.chart_template != CHART_TEMPLATE:
        _logger.info('pro_designed_setup: loading chart template %s for %s', CHART_TEMPLATE, COMPANY_NAME)
        env['account.chart.template'].try_loading(
            CHART_TEMPLATE, company=company, install_demo=False,
        )
        company.invalidate_recordset()
    else:
        _logger.info('pro_designed_setup: chart template already loaded for %s', COMPANY_NAME)

    # Set the VAT number on the company's partner.
    if company.partner_id.vat != COMPANY_VAT:
        company.partner_id.vat = COMPANY_VAT

    # Make sure the company is on EUR (should be set by the chart load).
    if company.currency_id != eur:
        company.currency_id = eur

    # Grant the admin user access to the company and make it the default one.
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    if admin:
        if company not in admin.company_ids:
            admin.company_ids = [(4, company.id)]
        admin.company_id = company

    _logger.info(
        'pro_designed_setup: done. company=%s currency=%s chart=%s vat=%s',
        company.name, company.currency_id.name, company.chart_template, company.partner_id.vat,
    )
