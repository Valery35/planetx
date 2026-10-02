# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Инсоляция по рельефу."""
import calendar
import math
import os
import sys
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid as el  # noqa: E402
import insolation as ins  # noqa: E402
import sun  # noqa: E402

LAT, LON = 58.0, 56.25  # Пермь
R = el.EARTH.a
SUMMER = calendar.timegm((2026, 6, 21, 0, 0, 0))
WINTER = calendar.timegm((2026, 12, 21, 0, 0, 0))


def flat(lats, lons):
    return np.zeros(np.shape(lats))


def day_length(lat, unix_time):
    """Длина дня без рефракции по склонению солнца в полдень, часы."""
    _, dec = sun.equatorial(unix_time)
    cos_h = -math.tan(math.radians(lat)) * math.tan(dec)
    return 2.0 * math.degrees(math.acos(max(-1.0, min(1.0, cos_h)))) / 15.0


def wall_south(lats, lons):
    """Стена 200 м шириной 300 м в 400-700 м к югу от точки."""
    dist, az = ins.distance_bearing(LAT, LON, lats, lons, R)
    south = (az > 135.0) & (az < 225.0)
    return np.where(south & (dist > 400.0) & (dist < 700.0), 200.0, 0.0)


def north_slope(lats, lons, steep=1.0):
    """Склон вниз к северу, тангенс уклона steep."""
    return (np.asarray(lats) - LAT) * -111000.0 * steep


def steep_north(lats, lons):
    """Склон 63.4° вниз к северу."""
    return north_slope(lats, lons, 2.0)


class TestInsolation(unittest.TestCase):

    def setUp(self):
        el.set_body(el.EARTH)

    def test_flat_is_day_length(self):
        # На ровной Земле часы прямого света - длина дня. Шаг 10 мин,
        # центр сутки UTC сдвинут от местного полдня: допуск 15 мин.
        for day in (SUMMER, WINTER):
            result = ins.compute(LAT, LON, 1000.0, flat, day, day)
            centre = result.hours[result.hours.shape[0] // 2,
                                  result.hours.shape[1] // 2]
            self.assertAlmostEqual(centre, day_length(LAT, day + 43200),
                                   delta=0.25)
            self.assertLess(np.ptp(result.hours), 0.2)

    def test_period_is_daily_mean(self):
        one = ins.compute(LAT, LON, 1000.0, flat, SUMMER, SUMMER)
        many = ins.compute(LAT, LON, 1000.0, flat, SUMMER - 3 * 86400,
                           SUMMER + 3 * 86400)
        self.assertEqual(many.days, 7)
        self.assertAlmostEqual(float(many.hours.mean()),
                               float(one.hours.mean()), delta=0.1)

    def test_wall_shades_north_side_in_winter(self):
        # Зимой солнце в Перми не выше 9°: за стеной 200 м в 400 м
        # к югу точка в тени весь день, к северу от точки на 2 км
        # тени нет.
        result = ins.compute(LAT, LON, 3000.0, wall_south, WINTER, WINTER)
        lat, lon = np.array([LAT, LAT + 0.018]), np.array([LON, LON])
        hours, inside = result.at(lat, lon, R)
        self.assertTrue(inside.all())
        self.assertLess(hours[0], 1.0)
        self.assertAlmostEqual(hours[1], day_length(LAT, WINTER + 43200),
                               delta=0.3)

    def test_north_slope_dark_in_winter(self):
        # Склон 45° на север зимой не получает прямого света. Летом
        # солнце в полдень выше 55°, он освещён почти весь день.
        # Склон 63.4° круче полуденного солнца, около полудня он
        # в тени, утром и вечером солнце на севере светит на него.
        winter = ins.compute(LAT, LON, 500.0, north_slope, WINTER, WINTER)
        self.assertLess(float(np.median(winter.hours)), 0.01)
        length = day_length(LAT, SUMMER + 43200)
        summer = ins.compute(LAT, LON, 500.0, north_slope, SUMMER, SUMMER)
        self.assertAlmostEqual(float(np.median(summer.hours)), length,
                               delta=0.3)
        steep = ins.compute(LAT, LON, 500.0, steep_north, SUMMER, SUMMER)
        self.assertGreater(float(np.median(steep.hours)), 6.0)
        self.assertLess(float(np.median(steep.hours)), length - 4.0)

    def test_colors_and_outside(self):
        result = ins.compute(LAT, LON, 1000.0, flat, SUMMER, SUMMER)
        rgba = ins.tile_rgba(result, np.array([LAT, LAT + 1.0]),
                             np.array([LON, LON]), R)
        self.assertGreater(rgba[0, 3], 0)
        self.assertEqual(int(rgba[1, 3]), 0)
        self.assertEqual(result.top, math.ceil(float(result.hours.max())))

    def test_month_10_km_is_fast(self):
        started = time.perf_counter()
        ins.compute(LAT, LON, 10000.0, flat, SUMMER, SUMMER + 30 * 86400)
        self.assertLess(time.perf_counter() - started, 20.0)


if __name__ == "__main__":
    unittest.main()
