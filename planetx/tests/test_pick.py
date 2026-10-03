# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Объекты под щелчком: расстояние до метки, пути, многоугольника."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid as el  # noqa: E402
import pick as pk  # noqa: E402


class TestPick(unittest.TestCase):

    def setUp(self):
        el.set_body(el.EARTH)

    def test_point_distance(self):
        # 0.01° широты - около 1112 м.
        gap = pk.distance("point", [(58.01, 56.0)], 58.0, 56.0)
        self.assertAlmostEqual(gap, 1112.0, delta=3.0)

    def test_line_nearest_segment(self):
        line = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0)]
        # Над серединой первого отрезка на 0.001° - около 111 м.
        self.assertAlmostEqual(pk.distance("line", line, 0.001, 0.5), 111.2,
                               delta=0.5)
        # Линия не замкнута: от точки у начала до последнего отрезка
        # далеко.
        self.assertGreater(pk.distance("line", line, 0.9, 0.0), 50000.0)

    def test_polygon_inside_is_zero(self):
        square = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
        self.assertEqual(pk.distance("polygon", square, 0.5, 0.5), 0.0)
        self.assertAlmostEqual(pk.distance("polygon", square, 0.5, 1.001),
                               111.2, delta=0.5)

    def test_picked_sorted_by_gap(self):
        shapes = [("point", [(0.0, 0.002)]), ("point", [(0.0, 0.001)]),
                  ("point", [(0.0, 1.0)])]
        self.assertEqual(pk.picked(shapes, 0.0, 0.0, 500.0), [1, 0])

    def test_dateline(self):
        gap = pk.distance("point", [(0.0, 179.999)], 0.0, -179.999)
        self.assertAlmostEqual(gap, 222.4, delta=0.5)

    def test_path_length(self):
        self.assertAlmostEqual(pk.path_length([(0.0, 0.0), (0.0, 1.0)]),
                               111195.0, delta=50.0)
        square = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
        self.assertAlmostEqual(pk.path_length(square, closed=True),
                               4 * 111195.0, delta=400.0)


if __name__ == "__main__":
    unittest.main()
