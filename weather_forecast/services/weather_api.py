# -*- coding: utf-8 -*-
"""
weather_api.py — Pure-Python service layer for OpenWeather One Call API 3.0.

Deliberately has NO dependency on the Odoo ORM so that:
  - Unit tests can run without a running Odoo instance.
  - The fetch and transform logic can be validated in isolation.

Public API
----------
  fetch_onecall(lat, lon, api_key, units, lang)  → raw API dict
  build_forecast_lines(data)                      → list[dict] ready for ORM upsert
  geocode_address(address)                        → (lat, lon)
"""

import logging
import requests
from datetime import datetime, timezone, timedelta

_logger = logging.getLogger(__name__)

# The OpenWeather hourly array covers exactly 48 hours.
HOURLY_WINDOW_HOURS = 48

# Nominatim User-Agent (required by OSM terms of service).
_GEOCODE_USER_AGENT = 'WeatherForecast/1.0 (Odoo module; Pro-Designed.com)'


# ---------------------------------------------------------------------------
# API fetch
# ---------------------------------------------------------------------------

def fetch_onecall(lat, lon, api_key, units='metric', lang='en'):
    """
    Call OpenWeather One Call API 3.0 and return the parsed JSON response.

    Excludes 'current', 'minutely', and 'alerts' to keep the response small —
    we only need hourly and daily forecasts.

    Raises:
        ValueError   — for auth errors (401) or rate-limit errors (429);
                       caller should surface these to the user as UserError.
        requests.HTTPError — for other HTTP errors.
        requests.RequestException — for network/timeout errors.
    """
    url = 'https://api.openweathermap.org/data/3.0/onecall'
    params = {
        'lat': lat,
        'lon': lon,
        'appid': api_key,
        'units': units,
        'exclude': 'current,minutely,alerts',
    }
    if lang:
        params['lang'] = lang

    _logger.info('Calling OpenWeather One Call API: lat=%s lon=%s units=%s', lat, lon, units)
    response = requests.get(url, params=params, timeout=15)

    if response.status_code == 401:
        raise ValueError(
            'OpenWeather API key is invalid or not activated. '
            'Please check your API key in Settings → Weather Forecast.'
        )
    if response.status_code == 429:
        raise ValueError(
            'OpenWeather API rate limit exceeded. '
            'Please wait before trying again or upgrade your API plan.'
        )

    response.raise_for_status()
    _logger.info('OpenWeather API response received (HTTP 200).')
    return response.json()


# ---------------------------------------------------------------------------
# Geocoding (Nominatim / OpenStreetMap)
# ---------------------------------------------------------------------------

def geocode_address(address):
    """
    Geocode a free-text address using the Nominatim API.

    Returns:
        (float lat, float lon)

    Raises:
        ValueError if the address yields no results.
        requests.RequestException on network errors.
    """
    url = 'https://nominatim.openstreetmap.org/search'
    params = {'q': address, 'format': 'json', 'limit': 1}
    headers = {'User-Agent': _GEOCODE_USER_AGENT}

    _logger.info('Geocoding address: %s', address)
    response = requests.get(url, params=params, headers=headers, timeout=10)
    response.raise_for_status()
    results = response.json()

    if not results:
        raise ValueError(
            f"Could not geocode address '{address}': no results found. "
            'Please enter a more specific address or set coordinates manually.'
        )

    lat = float(results[0]['lat'])
    lon = float(results[0]['lon'])
    _logger.info('Geocoded "%s" → lat=%.6f lon=%.6f', address, lat, lon)
    return lat, lon


# ---------------------------------------------------------------------------
# Forecast line builder
# ---------------------------------------------------------------------------

def _unix_to_utc(unix_ts):
    """
    Convert a Unix UTC timestamp (int) to a timezone-naive UTC datetime.
    Odoo datetime fields are always stored in UTC without tzinfo.
    """
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).replace(tzinfo=None)


def _get_temp_for_hour(hour, day, prev_day):
    """
    Map an hour-of-day (0-23) to the appropriate daily temperature period.

    Business rule: the daily forecast provides four temperature readings
    (morning, daytime, evening, night).  We approximate the continuous
    temperature curve by assigning each hour to the nearest period:

      00:00–06:59  →  night of the PREVIOUS day   (pre-dawn carry-over)
      07:00–10:59  →  morning of THIS day
      11:00–17:59  →  daytime of THIS day
      18:00–20:59  →  evening of THIS day
      21:00–23:59  →  night of THIS day

    The asymmetry at midnight is intentional: after midnight but before
    sunrise the temperature is still falling from the previous night.
    """
    if 0 <= hour <= 6:
        source = prev_day if prev_day else day
        return (
            source.get('temp', {}).get('night'),
            source.get('feels_like', {}).get('night'),
        )
    elif 7 <= hour <= 10:
        return (
            day.get('temp', {}).get('morn'),
            day.get('feels_like', {}).get('morn'),
        )
    elif 11 <= hour <= 17:
        return (
            day.get('temp', {}).get('day'),
            day.get('feels_like', {}).get('day'),
        )
    elif 18 <= hour <= 20:
        return (
            day.get('temp', {}).get('eve'),
            day.get('feels_like', {}).get('eve'),
        )
    else:  # 21-23
        return (
            day.get('temp', {}).get('night'),
            day.get('feels_like', {}).get('night'),
        )


def build_forecast_lines(data):
    """
    Transform a One Call API 3.0 response dict into a list of flat dicts,
    one dict per forecast hour, ready to upsert into weather.forecast.line.

    Design rationale — why store daily data as hourly records?
    ----------------------------------------------------------
    The consumer of this data (e.g. an energy/planning algorithm) expects
    a uniform, gapless hourly time series.  Mixing hourly and daily records
    in the same table would require the consumer to handle two different
    granularities.  By expanding daily entries into 24 synthetic hourly
    slots we provide a single consistent interface regardless of how far
    ahead the forecast extends.

    Strategy:
      1. Process the `hourly` array (first 48 h) as-is → source_type='hourly'
      2. Determine the cutoff: first datetime NOT covered by hourly data.
      3. For each day in the `daily` array, expand to hourly slots that fall
         AFTER the cutoff → source_type='daily'.  This prevents any overlap.

    Timezone handling:
      The API returns Unix UTC timestamps.  All stored datetimes are UTC-naive
      (as required by Odoo).  For daily expansion, we use `timezone_offset`
      from the API response to derive the correct LOCAL calendar date before
      building per-hour UTC datetimes.

    Returns:
        list[dict]  — keys match weather.forecast.line fields (no location_id).
    """
    now_utc = datetime.utcnow()
    # Seconds east of UTC for the forecast location — used to find local dates.
    tz_offset_seconds = data.get('timezone_offset', 0)

    hourly_data = data.get('hourly', [])
    daily_data = data.get('daily', [])

    lines = []
    hourly_datetimes = set()

    # -----------------------------------------------------------------------
    # PART 1 — Hourly records (source_type = 'hourly')
    # -----------------------------------------------------------------------
    for h in hourly_data:
        dt = _unix_to_utc(h['dt'])
        hourly_datetimes.add(dt)

        weather = (h.get('weather') or [{}])[0]
        # rain is a dict {"1h": mm} or absent
        rain_raw = h.get('rain')
        rain = rain_raw.get('1h') if isinstance(rain_raw, dict) else None

        lines.append({
            'forecast_datetime':      dt,
            'temperature':            h.get('temp'),
            'feels_like':             h.get('feels_like'),
            'humidity':               h.get('humidity'),
            'clouds':                 h.get('clouds'),
            'wind_speed':             h.get('wind_speed'),
            'rain':                   rain,
            'weather_id':             weather.get('id'),
            'weather_main':           weather.get('main'),
            'weather_description':    weather.get('description'),
            'source_type':            'hourly',
            'raw_api_datetime':       dt,
            'last_api_update_datetime': now_utc,
        })

    # -----------------------------------------------------------------------
    # PART 2 — Daily-to-hourly expansion (source_type = 'daily')
    # -----------------------------------------------------------------------
    # Any slot at or after this cutoff has NOT been covered by hourly data.
    if hourly_datetimes:
        cutoff_dt = max(hourly_datetimes) + timedelta(hours=1)
    else:
        cutoff_dt = now_utc

    for i, day in enumerate(daily_data):
        day_utc = _unix_to_utc(day['dt'])
        # Derive LOCAL calendar date for this daily entry.
        local_day_dt = day_utc + timedelta(seconds=tz_offset_seconds)
        local_date = local_day_dt.date()

        prev_day = daily_data[i - 1] if i > 0 else None
        weather = (day.get('weather') or [{}])[0]
        # Daily rain is the total accumulation for the day (mm).
        rain = day.get('rain')

        for hour in range(24):
            # Build the LOCAL datetime for this slot, then convert to UTC.
            local_slot_dt = datetime(
                local_date.year, local_date.month, local_date.day, hour, 0, 0
            )
            utc_slot_dt = local_slot_dt - timedelta(seconds=tz_offset_seconds)

            # Skip any slot already covered by the hourly array.
            if utc_slot_dt < cutoff_dt:
                continue

            temp, feels = _get_temp_for_hour(hour, day, prev_day)

            lines.append({
                'forecast_datetime':      utc_slot_dt,
                'temperature':            temp,
                'feels_like':             feels,
                'humidity':               day.get('humidity'),
                'clouds':                 day.get('clouds'),
                'wind_speed':             day.get('wind_speed'),
                'rain':                   rain,
                'weather_id':             weather.get('id'),
                'weather_main':           weather.get('main'),
                'weather_description':    weather.get('description'),
                'source_type':            'daily',
                'raw_api_datetime':       day_utc,
                'last_api_update_datetime': now_utc,
            })

    _logger.info(
        'build_forecast_lines: %d hourly + %d daily-expanded = %d total lines',
        len(hourly_datetimes),
        len(lines) - len(hourly_datetimes),
        len(lines),
    )
    return lines
