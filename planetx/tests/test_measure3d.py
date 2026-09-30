# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""3D-путь и 3D-многоугольник: попадание луча и меры в пространстве."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import measure3d as m3  # noqa: E402
from ellipsoid import geodetic_to_ecef, surface_normal  # noqa: E402


def box(x0, y0, x1, y1, h):
    """Треугольники коробки над плоскостью z = 0: крыша и четыре стены."""
    top = [(x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h)]
    low = [(x, y, 0.0) for x, y, _ in top]
    tris = [(top[0], top[1], top[2]), (top[0], top[2], top[3])]
    for i in range(4):
        j = (i + 1) % 4
        tris += [(low[i], low[j], top[j]), (low[i], top[j], top[i])]
    t = np.array(tris, dtype=np.float64)
    return t[:, 0], t[:, 1], t[:, 2]


class TestRay(unittest.TestCase):

    def test_roof_is_hit_from_above(self):
        a, b, c = box(0, 0, 10, 10, 20)
        t = m3.ray_triangles((5, 5, 100), (0, 0, -1), a, b, c)
        self.assertAlmostEqual(t, 80.0)

    def test_wall_is_hit_from_the_side(self):
        a, b, c = box(0, 0, 10, 10, 20)
        t = m3.ray_triangles((-30, 5, 10), (1, 0, 0), a, b, c)
        self.assertAlmostEqual(t, 30.0)

    def test_nearest_of_two_buildings(self):
        near = box(0, 0, 10, 10, 20)
        far = box(20, 0, 30, 10, 50)
        tris = [np.vstack([p, q]) for p, q in zip(near, far)]
        t = m3.ray_triangles((-10, 5, 15), (1, 0, 0), *tris)
        self.assertAlmostEqual(t, 10.0)

    def test_miss_and_behind(self):
        a, b, c = box(0, 0, 10, 10, 20)
        self.assertIsNone(m3.ray_triangles((50, 50, 100), (0, 0, -1),
                                           a, b, c))
        self.assertIsNone(m3.ray_triangles((5, 5, 100), (0, 0, 1), a, b, c))
        self.assertIsNone(m3.ray_triangles((5, 5, 100), (0, 0, -1),
                                           a[:0], b[:0], c[:0]))

    def test_sphere_filter(self):
        self.assertTrue(m3.ray_sphere((0, 0, 100), (0, 0, -1),
                                      (0, 0, 0), 5.0))
        self.assertFalse(m3.ray_sphere((0, 0, 100), (0, 0, 1),
                                       (0, 0, 0), 5.0))
        self.assertFalse(m3.ray_sphere((20, 0, 100), (0, 0, -1),
                                       (0, 0, 0), 5.0))


def local(lat, lon, east, north, up):
    """Точка ECEF в метрах от (lat, lon) по осям восток, север, вверх."""
    la, lo = math.radians(lat), math.radians(lon)
    e = np.array([-math.sin(lo), math.cos(lo), 0.0])
    n = np.array([-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo),
                  math.cos(la)])
    u = np.asarray(surface_normal(lat, lon), dtype=np.float64)
    return geodetic_to_ecef(lat, lon, 0.0) + east * e + north * n + up * u


class TestMeasures(unittest.TestCase):

    def test_path_is_straight_segments(self):
        p = [local(58, 56, 0, 0, 0), local(58, 56, 30, 0, 40),
             local(58, 56, 30, 0, 0)]
        self.assertAlmostEqual(m3.path_length(p), 50.0 + 40.0, places=6)

    def test_flat_roof(self):
        p = [local(58, 56, x, y, 25) for x, y in
             ((0, 0), (20, 0), (20, 10), (0, 10))]
        perimeter, area, tilt = m3.polygon(p)
        self.assertAlmostEqual(perimeter, 60.0, places=6)
        self.assertAlmostEqual(area, 200.0, places=4)
        self.assertLess(tilt, 0.01)

    def test_slope_of_30_degrees(self):
        # Скат 10 × 20 м под 30°: проекция на карту 10 × 17.32 м,
        # настоящая площадь 200 м².
        rise = 20.0 * math.sin(math.radians(30.0))
        run = 20.0 * math.cos(math.radians(30.0))
        p = [local(58, 56, 0, 0, 0), local(58, 56, 10, 0, 0),
             local(58, 56, 10, run, rise), local(58, 56, 0, run, rise)]
        _, area, tilt = m3.polygon(p)
        self.assertAlmostEqual(area, 200.0, places=3)
        self.assertAlmostEqual(tilt, 30.0, places=3)

    def test_wall(self):
        p = [local(58, 56, 0, 0, 0), local(58, 56, 12, 0, 0),
             local(58, 56, 12, 0, 9), local(58, 56, 0, 0, 9)]
        _, area, tilt = m3.polygon(p)
        self.assertAlmostEqual(area, 108.0, places=3)
        self.assertAlmostEqual(tilt, 90.0, places=3)

    def test_two_points(self):
        p = [local(58, 56, 0, 0, 0), local(58, 56, 3, 4, 0)]
        perimeter, area, tilt = m3.polygon(p)
        self.assertAlmostEqual(perimeter, 10.0, places=6)
        self.assertEqual((area, tilt), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
