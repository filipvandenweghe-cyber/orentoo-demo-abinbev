import logging

from odoo.tools import config

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
    #
    # Note: on demo builds we deliberately clear the `chart_template` marker
    # further down (see the demo-data compatibility guard), so we must not rely
    # on that marker alone to decide whether the chart is loaded — otherwise a
    # re-run (module update) would try to reload it. Treat the presence of
    # accounts as the source of truth.
    chart_already_loaded = company.chart_template == CHART_TEMPLATE or bool(
        env['account.account'].sudo().search_count(
            [('company_ids', 'in', company.id)], limit=1
        )
    )
    if not chart_already_loaded:
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

    # ------------------------------------------------------------------
    # Demo-data compatibility guard.
    #
    # Standard Odoo's `account.chart.template._install_demo()` iterates over
    # *every* company that has a chart of accounts
    # (`search([('chart_template', '!=', False)])`), but it resolves the demo
    # record XML-IDs (bank journal, bank account, ...) with `company_xmlid()`,
    # which is hard-wired to `self.env.company` — i.e. the *main* company —
    # instead of the company currently being processed. As a result it works
    # only when the main company is the single charted company.
    #
    # Because this module creates a *second* charted company, the account demo
    # would try to attach Pro-Designed.com's demo bank account to the main
    # company's bank journal and blow up with:
    #   "The partners of the journal's company and the related bank account
    #    mismatch."
    # which makes the whole `account` demo roll back ("installed without demo
    # data") and shows up on Odoo.sh as "failed to load demo data".
    #
    # The account demo runs later, during the demo phase (after all
    # post_init_hooks). To keep it from picking up this company we clear the
    # `chart_template` marker on demo builds only. The company keeps every
    # account, tax, journal and fiscal position that was just loaded and stays
    # fully operational (invoices post correctly); only the "which template was
    # loaded" marker is dropped so the buggy multi-company demo skips it.
    # Production/staging builds (no demo) keep the marker untouched.
    demo_enabled = not config.get('without_demo')
    if demo_enabled and company.chart_template:
        _logger.info(
            'pro_designed_setup: demo build detected — clearing chart_template '
            'marker on %s so the standard multi-company account demo skips it.',
            COMPANY_NAME,
        )
        company.sudo().write({'chart_template': False})

    _logger.info(
        'pro_designed_setup: done. company=%s currency=%s chart=%s vat=%s',
        company.name, company.currency_id.name, company.chart_template, company.partner_id.vat,
    )
