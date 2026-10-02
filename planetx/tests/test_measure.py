# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Линейка: окружность и единицы."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import numpy as np  # noqa: E402

import measure as ms  # noqa: E402
from ellipsoid import A  # noqa: E402


class TestDestination(unittest.TestCase):

    def test_north_degree(self):
        lat, lon = ms.destination(58.0, 56.0, 0.0, math.radians(1.0) * A)
        self.assertAlmostEqual(lat, 59.0, 9)
        self.assertAlmostEqual(lon, 56.0, 9)

    def test_east_on_equator(self):
        lat, lon = ms.destination(0.0, 179.5, 90.0, math.radians(1.0) * A)
        self.assertAlmostEqual(lat, 0.0, 9)
        self.assertAlmostEqual(lon, -179.5, 9)


class TestUnits(unittest.TestCase):

    def test_convert(self):
        self.assertEqual(ms.convert(2500.0, "km", ms.LENGTH_UNITS), 2.5)
        self.assertEqual(ms.convert(3.0e4, "ha", ms.AREA_UNITS), 3.0)

    def test_number(self):
        self.assertEqual(ms.number(12.345), "12.35")
        self.assertEqual(ms.number(12345.67), "12 345.7")
        self.assertEqual(ms.number(0.01234), "0.0123")


class TestProfile(unittest.TestCase):
    """Профиль высот и длина по рельефу."""

    def line(self, length):
        # Линия на север от Перми длиной length метров по сфере.
        end = ms.destination(58.0, 56.0, 0.0, length)
        return [(58.0, 56.0), end]

    def test_sampling_follows_pixel(self):
        points = ms.sample_line(self.line(1000.0))
        step = 1000.0 / (len(points) - 1)
        self.assertLessEqual(step, ms.pixel_size(58.0) * 1.01)
        self.assertGreater(step, ms.pixel_size(58.0) * 0.5)

    def test_long_line_is_limited(self):
        points = ms.sample_line(self.line(2.0e6))
        self.assertLessEqual(len(points), ms.PROFILE_POINTS)

    def test_ramp(self):
        latlon = ms.sample_line(self.line(1000.0))
        heights = latlon[:, 0] * 0.0
        heights = (latlon[:, 0] - 58.0) / (latlon[-1, 0] - 58.0) * 100.0
        p = ms.profile(latlon, heights)
        self.assertAlmostEqual(p.flat, 1000.0, delta=5.0)
        self.assertAlmostEqual(p.ground, math.hypot(p.flat, 100.0),
                               delta=0.5)
        self.assertAlmostEqual(p.gain, 100.0, places=6)
        self.assertAlmostEqual(p.loss, 0.0, places=6)
        self.assertAlmostEqual(p.mean_slope, 0.1, delta=0.001)
        self.assertAlmostEqual(p.max_slope, 0.1, delta=0.002)
        self.assertEqual((p.low, p.high), (0.0, 100.0))

    def test_slope_window_ignores_roughness(self):
        # Подъём 10 % с шероховатостью ±1.5 м через точку. Между
        # соседними точками уклон выходит за 50 %, на окне 50 м - нет.
        latlon = ms.sample_line(self.line(1000.0))
        p0 = ms.profile(latlon, latlon[:, 0] * 0.0)
        noise = np.where(np.arange(len(latlon)) % 2, 1.5, -1.5)
        heights = 0.1 * p0.distance + noise
        rough = ms.profile(latlon, heights)
        smooth = ms.profile(latlon, heights, window=50.0)
        self.assertGreater(rough.max_slope, 0.5)
        self.assertLess(smooth.max_slope, 0.2)
        self.assertAlmostEqual(smooth.mean_slope, 0.1, delta=0.02)

    def test_up_and_down(self):
        latlon = ms.sample_line(self.line(2000.0))
        t = (latlon[:, 0] - 58.0) / (latlon[-1, 0] - 58.0)
        heights = 200.0 - 150.0 * abs(2.0 * t - 1.0)  # вверх и вниз
        p = ms.profile(latlon, heights)
        self.assertAlmostEqual(p.gain, 150.0, delta=0.5)
        self.assertAlmostEqual(p.loss, 150.0, delta=0.5)

    def test_ground_length_flat(self):
        points = self.line(5000.0)
        ground = ms.ground_length(points, lambda lats, lons: lats * 0.0)
        # Хорды через пиксель на эллипсоиде против дуги на сфере.
        self.assertAlmostEqual(ground, 5000.0, delta=20.0)

    def test_level_and_tiles(self):
        short = self.line(1000.0)
        long_ = self.line(1.0e6)
        self.assertEqual(ms.height_level(short), 15)
        level = ms.height_level(long_)
        self.assertLess(level, 15)
        self.assertGreaterEqual(ms.pixel_size(58.0, level),
                                1.0e6 / ms.PROFILE_POINTS * 0.99)
        keys = ms.tiles_along(ms.sample_line(long_), level)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(k[0] == level for k in keys))

    def test_bearing(self):
        self.assertAlmostEqual(ms.bearing(58.0, 56.0, 59.0, 56.0), 0.0)
        self.assertAlmostEqual(ms.bearing(0.0, 0.0, 0.0, 1.0), 90.0)

    def test_nearest_vertex(self):
        pixels = [(100.0, 100.0), (200.0, 105.0), (300.0, 100.0)]
        self.assertEqual(ms.nearest_vertex(pixels, [True] * 3, 198, 100, 8),
                         1)
        self.assertIsNone(ms.nearest_vertex(pixels, [True] * 3, 150, 100, 8))
        # Точка за камерой не хватается.
        self.assertIsNone(ms.nearest_vertex(pixels, [True, False, True],
                                            198, 100, 8))

    def test_midpoints(self):
        mids = ms.segment_midpoints([(58.0, 56.0), (58.0, 57.0),
                                     (59.0, 57.0)], closed=True)
        self.assertEqual(len(mids), 3)
        self.assertAlmostEqual(mids[0][1], 56.5, places=6)
        self.assertAlmostEqual(mids[1][0], 58.5, delta=1e-3)
        # Геодезическая, а не геоцентрическая широта.
        mid = ms.segment_midpoints([(45.0, 10.0), (45.0, 10.002)])[0]
        self.assertAlmostEqual(mid[0], 45.0, delta=1e-6)
class TestSurfaceLevel(unittest.TestCase):

    def test_below_sea_is_depth(self):
        self.assertEqual(ms.surface_level(-10565.4), ("depth", 10565))
        self.assertEqual(ms.surface_level(-0.3), ("height", 0))
        self.assertEqual(ms.surface_level(207.6), ("height", 208))


if __name__ == "__main__":
    unittest.main()
