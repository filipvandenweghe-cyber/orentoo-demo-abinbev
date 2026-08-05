# -*- coding: utf-8 -*-
"""
Extends res.config.settings with Weather Forecast configuration:
  - OpenWeather API key
  - Units  (metric / imperial / standard)
  - Daily automatic update time  (HH:MM in company timezone)
  - API language

When settings are saved, the scheduled cron nextcall is recalculated so it
fires at the configured local time on the following day.
"""

import logging
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_DEFAULT_API_KEY = '7c82d953473419821761dc7defe78493'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # -----------------------------------------------------------------------
    # Configuration fields — stored via ir.config_parameter
    # -----------------------------------------------------------------------

    weather_api_key = fields.Char(
        string='OpenWeather API Key',
        config_parameter='weather_forecast.api_key',
        default=_DEFAULT_API_KEY,
        help='API key for OpenWeather One Call API 3.0.',
    )
    weather_units = fields.Selection(
        string='Units',
        config_parameter='weather_forecast.units',
        selection=[
            ('metric',   'Metric (°C, m/s)'),
            ('imperial', 'Imperial (°F, mph)'),
            ('standard', 'Standard (Kelvin, m/s)'),
        ],
        default='metric',
    )
    weather_update_time = fields.Char(
        string='Daily Update Time (HH:MM)',
        config_parameter='weather_forecast.update_time',
        default='16:00',
        help=(
            'Time of day at which the automatic weather update runs, '
            'expressed in the company timezone.  Format: HH:MM (24h).'
        ),
    )
    weather_language = fields.Char(
        string='API Language',
        config_parameter='weather_forecast.language',
        default='en',
        help=(
            'ISO 639-1 language code for weather descriptions returned by the API '
            '(e.g. "en", "nl", "fr").  Leave blank to use English.'
        ),
    )

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def set_values(self):
        """
        After saving settings, recalculate the cron nextcall so the scheduled
        update runs at the newly configured local time.
        """
        super().set_values()
        self._update_weather_cron_schedule()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _update_weather_cron_schedule(self):
        """
        Recompute and write the nextcall datetime on the weather forecast cron.

        Steps:
          1. Parse the configured HH:MM time.
          2. Resolve the company timezone.
          3. Build a timezone-aware next-run datetime for today (or tomorrow
             if today's slot has already passed).
          4. Convert to UTC and write to ir.cron.nextcall.
        """
        raw_time = (self.weather_update_time or '16:00').strip()
        try:
            hour, minute = map(int, raw_time.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except (ValueError, AttributeError):
            _logger.warning(
                'Invalid weather_update_time "%s"; defaulting cron to 16:00.', raw_time
            )
            hour, minute = 16, 0

        tz_name = self.env.company.partner_id.tz or 'UTC'
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            _logger.warning('Unknown timezone "%s"; using UTC for cron schedule.', tz_name)
            tz = pytz.UTC

        now_local = datetime.now(tz)
        next_run_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run_local <= now_local:
            next_run_local += timedelta(days=1)

        # Odoo stores datetime fields as UTC without tzinfo.
        next_run_utc = next_run_local.astimezone(pytz.UTC).replace(tzinfo=None)

        cron = self.env.ref(
            'weather_forecast.ir_cron_weather_update', raise_if_not_found=False
        )
        if cron:
            cron.sudo().write({'nextcall': next_run_utc})
            _logger.info(
                'Weather cron nextcall set to %s UTC (configured: %s %s).',
                next_run_utc, raw_time, tz_name,
            )
