# -*- coding: utf-8 -*-
"""
weather.forecast.line — one record per forecast hour per location.

Business rule: ALL records are stored at hourly granularity even when the
underlying data comes from a daily forecast.  See services/weather_api.py →
build_forecast_lines() for the expansion logic and the rationale.
"""

from odoo import fields, models


class WeatherForecastLine(models.Model):
    _name = 'weather.forecast.line'
    _description = 'Weather Forecast Line'
    _order = 'forecast_datetime asc'

    # -----------------------------------------------------------------------
    # Relational
    # -----------------------------------------------------------------------
    location_id = fields.Many2one(
        comodel_name='weather.location',
        string='Location',
        required=True,
        ondelete='cascade',
        index=True,
    )

    # -----------------------------------------------------------------------
    # Time
    # -----------------------------------------------------------------------
    forecast_datetime = fields.Datetime(
        string='Forecast Date/Time (UTC)',
        required=True,
        index=True,
        help='The UTC datetime this forecast line applies to.',
    )

    # -----------------------------------------------------------------------
    # Atmospheric data
    # -----------------------------------------------------------------------
    temperature = fields.Float(
        string='Temperature',
        digits=(6, 2),
        help='Temperature in the configured units (°C / °F / K).',
    )
    feels_like = fields.Float(
        string='Feels Like',
        digits=(6, 2),
        help='Human-perceived temperature (wind chill / heat index).',
    )
    humidity = fields.Float(
        string='Humidity (%)',
        digits=(5, 1),
        help='Relative humidity, percentage.',
    )
    clouds = fields.Float(
        string='Cloud Cover (%)',
        digits=(5, 1),
        help='Cloudiness, percentage.',
    )
    wind_speed = fields.Float(
        string='Wind Speed',
        digits=(6, 2),
        help='Wind speed in m/s (metric/standard) or mph (imperial).',
    )
    rain = fields.Float(
        string='Rain (mm)',
        digits=(6, 2),
        help=(
            'Precipitation volume.  For hourly lines: mm in the preceding hour.  '
            'For daily-expanded lines: total daily accumulation in mm.'
        ),
    )

    # -----------------------------------------------------------------------
    # Weather condition
    # -----------------------------------------------------------------------
    weather_id = fields.Integer(
        string='Weather Condition ID',
        help='OpenWeather weather condition code (see openweathermap.org/weather-conditions).',
    )
    weather_main = fields.Char(
        string='Weather Main',
        help='Group of weather parameters: Rain, Snow, Clouds, etc.',
    )
    weather_description = fields.Char(
        string='Weather Description',
        help='Human-readable weather condition description.',
    )

    # -----------------------------------------------------------------------
    # Metadata / provenance
    # -----------------------------------------------------------------------
    source_type = fields.Selection(
        string='Source Type',
        selection=[
            ('hourly', 'Hourly'),
            ('daily', 'Daily (expanded)'),
        ],
        help=(
            '"Hourly" = data came directly from the API hourly array.  '
            '"Daily (expanded)" = data was derived by expanding a daily forecast '
            'record into hourly slots using time-block temperature mapping.'
        ),
    )
    raw_api_datetime = fields.Datetime(
        string='API Record Datetime (UTC)',
        help='The dt timestamp of the source API record (hourly or daily).',
    )
    last_api_update_datetime = fields.Datetime(
        string='Last API Update (UTC)',
        help='UTC timestamp of the most recent API call that wrote this record.',
    )

    # -----------------------------------------------------------------------
    # Constraints
    # -----------------------------------------------------------------------
    _unique_location_forecast_datetime = models.Constraint(
        'UNIQUE(location_id, forecast_datetime)',
        'A forecast line for this location and datetime already exists.',
    )
