# -*- coding: utf-8 -*-
"""
Tests for the weather_api service layer.

These tests cover the pure-Python transformation logic in
services/weather_api.py and do NOT require a running Odoo database.
They can be run with:

    python -m pytest weather_forecast/tests/test_weather_service.py -v

For Odoo test runner:
    odoo -d <db> --test-enable --stop-after-init -i weather_forecast
"""

import unittest
from datetime import datetime, timezone, timedelta

from ..services.weather_api import (
    _unix_to_utc,
    _get_temp_for_hour,
    build_forecast_lines,
    HOURLY_WINDOW_HOURS,
)


def _make_hourly_entry(unix_ts, temp=20.0, feels=19.0, humidity=60, clouds=25,
                       wind=5.0, rain_1h=None, weather_id=800,
                       weather_main='Clear', weather_desc='clear sky'):
    """Build a minimal mock hourly API entry."""
    entry = {
        'dt': unix_ts,
        'temp': temp,
        'feels_like': feels,
        'humidity': humidity,
        'clouds': clouds,
        'wind_speed': wind,
        'weather': [{'id': weather_id, 'main': weather_main, 'description': weather_desc}],
    }
    if rain_1h is not None:
        entry['rain'] = {'1h': rain_1h}
    return entry


def _make_daily_entry(unix_ts, temp_day=22.0, temp_night=14.0, temp_morn=17.0,
                      temp_eve=19.0, feels_day=21.0, feels_night=13.0,
                      feels_morn=16.0, feels_eve=18.0,
                      humidity=55, clouds=30, wind=4.5, rain=2.0,
                      weather_id=500, weather_main='Rain',
                      weather_desc='light rain'):
    """Build a minimal mock daily API entry."""
    return {
        'dt': unix_ts,
        'temp': {
            'day': temp_day, 'night': temp_night,
            'morn': temp_morn, 'eve': temp_eve,
        },
        'feels_like': {
            'day': feels_day, 'night': feels_night,
            'morn': feels_morn, 'eve': feels_eve,
        },
        'humidity': humidity,
        'clouds': clouds,
        'wind_speed': wind,
        'rain': rain,
        'weather': [{'id': weather_id, 'main': weather_main, 'description': weather_desc}],
    }


class TestUnixToUtc(unittest.TestCase):

    def test_known_timestamp(self):
        # Unix 0 = 1970-01-01 00:00:00 UTC
        result = _unix_to_utc(0)
        self.assertEqual(result, datetime(1970, 1, 1, 0, 0, 0))
        self.assertIsNone(result.tzinfo)  # Odoo expects tz-naive UTC


class TestGetTempForHour(unittest.TestCase):

    def setUp(self):
        self.day = {
            'temp': {'morn': 15.0, 'day': 22.0, 'eve': 19.0, 'night': 12.0},
            'feels_like': {'morn': 14.0, 'day': 21.0, 'eve': 18.0, 'night': 11.0},
        }
        self.prev_day = {
            'temp': {'night': 10.0},
            'feels_like': {'night': 9.0},
        }

    def test_midnight_uses_prev_night(self):
        temp, feels = _get_temp_for_hour(0, self.day, self.prev_day)
        self.assertEqual(temp, 10.0)   # prev_day night
        self.assertEqual(feels, 9.0)

    def test_06_still_uses_prev_night(self):
        temp, _ = _get_temp_for_hour(6, self.day, self.prev_day)
        self.assertEqual(temp, 10.0)

    def test_07_uses_morning(self):
        temp, feels = _get_temp_for_hour(7, self.day, self.prev_day)
        self.assertEqual(temp, 15.0)
        self.assertEqual(feels, 14.0)

    def test_12_uses_day(self):
        temp, _ = _get_temp_for_hour(12, self.day, self.prev_day)
        self.assertEqual(temp, 22.0)

    def test_18_uses_evening(self):
        temp, _ = _get_temp_for_hour(18, self.day, self.prev_day)
        self.assertEqual(temp, 19.0)

    def test_21_uses_night(self):
        temp, _ = _get_temp_for_hour(21, self.day, self.prev_day)
        self.assertEqual(temp, 12.0)

    def test_no_prev_day_midnight_falls_back_to_current(self):
        """When there is no previous day (first daily entry), use current day night."""
        temp, _ = _get_temp_for_hour(0, self.day, None)
        self.assertEqual(temp, 12.0)


class TestBuildForecastLines(unittest.TestCase):
    """
    Integration-style tests for build_forecast_lines using mock API responses.
    """

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _make_api_data(hourly_count=48, daily_count=8, tz_offset=3600):
        """Build a minimal mock One Call API response."""
        base_ts = int(datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        hourly = [
            _make_hourly_entry(base_ts + i * 3600)
            for i in range(hourly_count)
        ]
        # Daily starts from current day at local noon
        daily_base = int(datetime(2024, 6, 1, 11, 0, 0, tzinfo=timezone.utc).timestamp())  # noon local (tz_offset=3600)
        daily = [
            _make_daily_entry(daily_base + i * 86400)
            for i in range(daily_count)
        ]
        return {'hourly': hourly, 'daily': daily, 'timezone_offset': tz_offset}

    # ---- tests -------------------------------------------------------------

    def test_hourly_records_count(self):
        data = self._make_api_data(hourly_count=48, daily_count=0)
        lines = build_forecast_lines(data)
        self.assertEqual(len(lines), 48)

    def test_all_hourly_have_source_type_hourly(self):
        data = self._make_api_data(hourly_count=10, daily_count=0)
        lines = build_forecast_lines(data)
        self.assertTrue(all(l['source_type'] == 'hourly' for l in lines))

    def test_daily_lines_have_source_type_daily(self):
        data = self._make_api_data(hourly_count=48, daily_count=4)
        lines = build_forecast_lines(data)
        daily_lines = [l for l in lines if l['source_type'] == 'daily']
        self.assertGreater(len(daily_lines), 0)
        self.assertTrue(all(l['source_type'] == 'daily' for l in daily_lines))

    def test_no_overlap_between_hourly_and_daily(self):
        data = self._make_api_data(hourly_count=48, daily_count=8)
        lines = build_forecast_lines(data)
        hourly_dts = {l['forecast_datetime'] for l in lines if l['source_type'] == 'hourly'}
        daily_dts  = {l['forecast_datetime'] for l in lines if l['source_type'] == 'daily'}
        self.assertEqual(hourly_dts & daily_dts, set(), 'Hourly and daily datetimes must not overlap')

    def test_forecast_datetimes_are_tz_naive(self):
        data = self._make_api_data()
        lines = build_forecast_lines(data)
        for line in lines:
            self.assertIsNone(
                line['forecast_datetime'].tzinfo,
                'forecast_datetime must be tz-naive UTC for Odoo compatibility',
            )

    def test_rain_is_none_when_absent(self):
        data = self._make_api_data(hourly_count=2, daily_count=0)
        # No 'rain' key in the hourly entry
        lines = build_forecast_lines(data)
        for line in lines:
            self.assertIsNone(line.get('rain'))

    def test_rain_extracted_from_hourly_dict(self):
        base_ts = int(datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        data = {
            'hourly': [_make_hourly_entry(base_ts, rain_1h=1.5)],
            'daily': [],
            'timezone_offset': 0,
        }
        lines = build_forecast_lines(data)
        self.assertEqual(lines[0]['rain'], 1.5)

    def test_empty_response_returns_empty_list(self):
        lines = build_forecast_lines({'hourly': [], 'daily': [], 'timezone_offset': 0})
        self.assertEqual(lines, [])

    def test_all_lines_have_last_api_update_datetime(self):
        data = self._make_api_data(hourly_count=5, daily_count=2)
        lines = build_forecast_lines(data)
        for line in lines:
            self.assertIn('last_api_update_datetime', line)
            self.assertIsNotNone(line['last_api_update_datetime'])


if __name__ == '__main__':
    unittest.main()
