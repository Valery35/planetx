# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Свои объекты глобуса: сгущение, посадка, треугольники."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid as el  # noqa: E402
import features as ft  # noqa: E402


class TestDensify(unittest.TestCase):

    def test_step_along_arc(self):
        # Градус меридиана - около 111 км, при шаге 100 м ~1113 точек.
        out = ft.densify([(58.0, 56.0), (59.0, 56.0)])
        self.assertEqual(tuple(out[0]), (58.0, 56.0))
        self.assertAlmostEqual(out[-1][0], 59.0)
        self.assertTrue(1100 < len(out) < 1130)
        self.assertTrue(np.all(np.diff(out[:, 0]) > 0))

    def test_great_circle_bulges_to_pole(self):
        # Дуга между точками одной параллели идёт севернее её.
        out = ft.densify([(60.0, 0.0), (60.0, 40.0)], step=10000.0)
        self.assertGreater(out[:, 0].max(), 61.0)

    def test_point_cap(self):
        out = ft.densify([(0.0, 0.0), (0.0, 90.0)], max_points=500)
        self.assertLessEqual(len(out), 500)

    def test_closed_ring_returns_to_start_without_repeat(self):
        ring = [(0.0, 0.0), (0.0, 0.01), (0.01, 0.01)]
        out = ft.densify(ring, closed=True, step=200.0)
        self.assertEqual(tuple(out[0]), (0.0, 0.0))
        self.assertFalse(np.allclose(out[-1], out[0]))

    def test_short(self):
        self.assertEqual(len(ft.densify([(1.0, 2.0)])), 1)


class TestLift(unittest.TestCase):

    def test_heights_and_center(self):
        latlon = np.array([[58.0, 56.0], [58.01, 56.01]])
        xyz = ft.lift(latlon, lambda lat, lon: 150.0)
        lat, lon, h = el.ecef_to_geodetic(xyz[0])
        self.assertAlmostEqual(float(h), 150.0, 3)
        center, offsets = ft.centered(xyz)
        self.assertEqual(offsets.dtype, np.float32)
        # Смещения малы, float32 их держит до сантиметров.
        back = center + offsets.astype(np.float64)
        self.assertLess(np.abs(back - xyz).max(), 0.01)


class TestSegments(unittest.TestCase):

    def test_open_and_closed(self):
        self.assertEqual(list(ft.segments(3)), [0, 1, 1, 2])
        self.assertEqual(list(ft.segments(3, closed=True)),
                         [0, 1, 1, 2, 2, 0])


class TestTriangulate(unittest.TestCase):

    def area(self, p, tri):
        total = 0.0
        for i in range(0, len(tri), 3):
            a, b, c = p[tri[i]], p[tri[i + 1]], p[tri[i + 2]]
            total += abs((b[0] - a[0]) * (c[1] - a[1])
                         - (b[1] - a[1]) * (c[0] - a[0])) / 2.0
        return total

    def test_square_both_orders(self):
        sq = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        for p in (sq, sq[::-1]):
            tri = ft.triangulate(p)
            self.assertEqual(len(tri), 6)
            self.assertAlmostEqual(self.area(p, tri), 1.0)

    def test_concave_l_shape(self):
        p = np.array([[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2]],
                     dtype=float)
        tri = ft.triangulate(p)
        self.assertEqual(len(tri), 12)
        self.assertAlmostEqual(self.area(p, tri), 3.0)

    def test_plane_of_small_polygon(self):
        xy = ft.plane([(58.0, 56.0), (58.0, 56.01), (58.01, 56.01)])
        # 0.01° долготы на 58° - около 590 м.
        self.assertAlmostEqual(abs(xy[1, 0] - xy[0, 0]), 590.0, delta=5.0)


if __name__ == "__main__":
    unittest.main()
