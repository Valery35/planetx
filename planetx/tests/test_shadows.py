# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тени на момент по рельефу."""
import calendar
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid as el  # noqa: E402
import insolation as ins  # noqa: E402
import shadows  # noqa: E402

LAT, LON = 58.0, 56.25  # Пермь
R = el.EARTH.a
# Местный полдень 21 декабря - около 8:15 UTC, солнце на юге не выше 9°.
WINTER_NOON = calendar.timegm((2026, 12, 21, 8, 15, 0))
SUMMER_NOON = calendar.timegm((2026, 6, 21, 8, 15, 0))
NIGHT = calendar.timegm((2026, 6, 21, 22, 0, 0))


def flat(lats, lons):
    return np.zeros(np.shape(lats))


def wall_south(lats, lons):
    """Стена 200 м шириной 300 м в 400-700 м к югу от точки."""
    dist, az = ins.distance_bearing(LAT, LON, lats, lons, R)
    south = (az > 135.0) & (az < 225.0)
    return np.where(south & (dist > 400.0) & (dist < 700.0), 200.0, 0.0)


def hill(lats, lons):
    """Холм 300 м радиусом 1 км в 1.5 км к югу от точки."""
    dist, az = ins.distance_bearing(LAT, LON, lats, lons, R)
    north = dist * np.cos(np.radians(az))
    east = dist * np.sin(np.radians(az))
    r = np.hypot(north + 1500.0, east)
    return np.where(r < 1000.0, 300.0 * (1.0 - r / 1000.0), 0.0)


def centre_lit(result):
    n = result.lit.shape[0]
    return bool(result.lit[n // 2, n // 2])


class TestShadows(unittest.TestCase):

    def setUp(self):
        el.set_body(el.EARTH)

    def test_flat_ground_is_lit_by_day(self):
        result = shadows.compute(LAT, LON, 1000.0, flat).at(SUMMER_NOON)
        self.assertTrue(result.lit.all())
        self.assertGreater(result.elevation, 50.0)

    def test_sun_below_horizon_shades_everything(self):
        result = shadows.compute(LAT, LON, 1000.0, flat).at(NIGHT)
        self.assertLess(result.elevation, 0.0)
        self.assertFalse(result.lit.any())

    def test_wall_shades_north_of_it_in_winter_noon(self):
        horizon = shadows.compute(LAT, LON, 1000.0, wall_south)
        self.assertFalse(centre_lit(horizon.at(WINTER_NOON)))
        # Летом солнце выше 50°, стена 200 м в 400 м тени не даёт.
        self.assertTrue(centre_lit(horizon.at(SUMMER_NOON)))

    def test_hill_shades_point_but_not_far_north(self):
        horizon = shadows.compute(LAT, LON, 1000.0, hill)
        winter = horizon.at(WINTER_NOON)
        self.assertFalse(centre_lit(winter))
        # 900 м к северу от точки угол на холм меньше высоты солнца.
        n = winter.lit.shape[0]
        north = n // 2 + int(900.0 / winter.cell)
        self.assertTrue(bool(winter.lit[north, n // 2]))

    def test_raster_and_tile(self):
        result = shadows.compute(LAT, LON, 500.0, wall_south, ring=[
            (LAT - 0.002, LON - 0.002), (LAT - 0.002, LON + 0.002),
            (LAT + 0.002, LON + 0.002), (LAT + 0.002, LON - 0.002)]
        ).at(WINTER_NOON)
        north, west, dlat, dlon, grid = shadows.raster(result)
        self.assertGreater(north, LAT)
        self.assertLess(west, LON)
        values = set(np.unique(grid).tolist())
        self.assertTrue(values <= {shadows.SUN, shadows.SHADE,
                                   shadows.OUTSIDE})
        self.assertIn(shadows.OUTSIDE, values)
        self.assertIn(shadows.SHADE, values)
        lats, lons = np.meshgrid(np.linspace(LAT - 0.01, LAT + 0.01, 8),
                                 np.linspace(LON - 0.01, LON + 0.01, 8),
                                 indexing="ij")
        rgba = shadows.tile_rgba(result, lats, lons, R)
        self.assertEqual(rgba.shape, (8, 8, 4))
        self.assertEqual(int(rgba[0, 0, 3]), 0)  # вне участка прозрачно
        self.assertTrue(0.0 <= result.share() <= 1.0)

    def test_azimuths_between_bins_interpolate(self):
        hor = np.zeros((4, 2, 2), dtype=np.float32)
        hor[0] = 1.0  # север - горизонт 45°
        normal = (np.zeros((2, 2)), np.zeros((2, 2)), np.ones((2, 2)))
        el_tan = math.tan(math.radians(30.0))
        north = (0.0, 1.0, el_tan)
        east = (1.0, 0.0, el_tan)
        self.assertFalse(shadows.lit_map(hor, normal, north).any())
        self.assertTrue(shadows.lit_map(hor, normal, east).all())


if __name__ == "__main__":
    unittest.main()
