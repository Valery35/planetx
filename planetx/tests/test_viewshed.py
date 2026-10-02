# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Видимость из точки по рельефу."""
import math
import os
import sys
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid as el  # noqa: E402
import viewshed as vs  # noqa: E402

LAT, LON = 45.0, 10.0
R = el.EARTH.a


def flat(lats, lons):
    return np.zeros(np.shape(lats))


def wall(lats, lons):
    """Стена высотой 100 м в 1-2 км к востоку от точки."""
    dist, az = vs.distance_bearing(LAT, LON, lats, lons, R)
    east = (az > 45.0) & (az < 135.0)
    return np.where(east & (dist > 1000.0) & (dist < 2000.0), 100.0, 0.0)


class TestViewshed(unittest.TestCase):

    def setUp(self):
        el.set_body(el.EARTH)

    def test_flat_horizon(self):
        # На ровной Земле глаз на 2 м видит землю до горизонта
        # sqrt(2·R'·h), с рефракцией 0.13 около 5.4 км.
        result = vs.compute(LAT, LON, 10000.0, 50.0, flat, observer=2.0)
        horizon = math.sqrt(2.0 * R / (1.0 - vs.REFRACTION) * 2.0)
        seen = result.visible[0]
        last = (np.nonzero(seen)[0].max() + 1) * result.step
        self.assertAlmostEqual(last, horizon, delta=2 * result.step)

    def test_wall_hides_behind(self):
        result = vs.compute(LAT, LON, 5000.0, 20.0, wall, observer=2.0)
        lat, lon = vs.destinations(LAT, LON, np.array([[90.0]]),
                                   np.array([[900.0, 1500.0, 3000.0]]), R)
        seen, inside = result.at(lat.ravel(), lon.ravel(), R)
        self.assertTrue(inside.all())
        # Перед стеной видно. Плоский верх стены выше глаза на 2 м
        # не виден, за стеной тоже. К западу видно до 3 км.
        self.assertEqual(seen.tolist(), [True, False, False])
        west = vs.destinations(LAT, LON, np.array([[270.0]]),
                               np.array([[3000.0]]), R)
        self.assertTrue(result.at(west[0].ravel(), west[1].ravel(),
                                  R)[0][0])

    def test_mast_sees_over_wall(self):
        result = vs.compute(LAT, LON, 5000.0, 20.0, wall, observer=300.0)
        lat, lon = vs.destinations(LAT, LON, np.array([[90.0]]),
                                   np.array([[1500.0, 3000.0]]), R)
        # С мачты 300 м видны и верх стены, и земля за ней.
        self.assertTrue(result.at(lat.ravel(), lon.ravel(), R)[0].all())

    def test_outside_and_colors(self):
        result = vs.compute(LAT, LON, 1000.0, 20.0, flat)
        rgba = vs.tile_rgba(result, np.array([LAT, LAT + 1.0]),
                            np.array([LON + 0.001, LON]), R)
        self.assertGreater(rgba[0, 3], 0)
        self.assertEqual(int(rgba[1, 3]), 0)

    def test_height_tiles_cover_circle(self):
        # 10 км, шаг 20 м: пиксель уровня не крупнее шага, тайлов
        # не больше MAX_TILES, рамка круга внутри тайлов.
        level, keys = vs.height_tiles(LAT, LON, 10000.0, 20.0, R, 15)
        ground = 2 * math.pi * R * math.cos(math.radians(LAT)) / 256
        self.assertLessEqual(len(keys), vs.MAX_TILES)
        south, north, west, east = vs.circle_box(LAT, LON, 10000.0, R)
        n = 1 << level
        xs = [k[1] for k in keys]
        self.assertLessEqual(min(xs) / n * 360 - 180, west)
        self.assertGreaterEqual((max(xs) + 1) / n * 360 - 180, east)
        # Уровень мог уменьшиться ради количества тайлов, но не ниже
        # того, где пиксель вдвое крупнее шага на каждую ступень.
        self.assertGreater(level, 8)
        self.assertLess(ground / 2 ** (level + 1), 20.0)
        # Предел уровня источника соблюдается.
        level, _ = vs.height_tiles(LAT, LON, 1000.0, 2.0, R, 5)
        self.assertEqual(level, 5)

    def test_50_km_is_fast(self):
        # Критерий плана: радиус 50 км не дольше 5 с, расчёт без загрузки.
        started = time.perf_counter()
        vs.compute(LAT, LON, 50000.0, 100.0, flat)
        self.assertLess(time.perf_counter() - started, 5.0)


if __name__ == "__main__":
    unittest.main()
