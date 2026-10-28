# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты анализа рельефа квадрата: уклон, сводка, раскраска тайла."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import hydro  # noqa: E402
import relief  # noqa: E402

R = 6371000.0


def east_plane(grid, gradient):
    """Высоты, падающие на восток с уклоном gradient."""
    cols = np.arange(grid.cols, dtype=np.float64)
    return np.tile(1000.0 - cols * gradient * grid.cell, (grid.rows, 1))


class TestAnalyse(unittest.TestCase):

    def setUp(self):
        self.grid = hydro.make_grid(55.0, 37.0, 500.0, 10.0, R)

    def test_east_plane_slope_and_aspect(self):
        result = relief.analyse(east_plane(self.grid, 0.2), self.grid, R)
        inner = (slice(1, -1), slice(1, -1))
        self.assertTrue(np.allclose(result.slope[inner],
                                    math.degrees(math.atan(0.2))))
        self.assertTrue(np.allclose(result.aspect[inner], 90.0))
        south, north, west, east = result.box
        self.assertLess(south, 55.0)
        self.assertGreater(north, 55.0)
        self.assertLess(west, 37.0)
        self.assertGreater(east, 37.0)

    def test_flat_has_no_aspect(self):
        result = relief.analyse(np.full((self.grid.rows, self.grid.cols),
                                        200.0), self.grid, R)
        self.assertTrue(np.isnan(result.aspect).all())
        rep = relief.summary(result)
        self.assertEqual(rep.flat, 1.0)
        self.assertEqual(sum(rep.sides), 0.0)

    def test_summary_areas_and_sides(self):
        result = relief.analyse(east_plane(self.grid, 0.2), self.grid, R)
        rep = relief.summary(result)
        total = self.grid.rows * self.grid.cols * self.grid.cell ** 2
        self.assertAlmostEqual(sum(a for _, a in rep.classes), total)
        # 11.3° - класс от 10°, у крайних столбцов ядро даёт половину.
        area = dict(rep.classes)[10.0]
        edge = 2 * self.grid.rows * self.grid.cell ** 2
        self.assertAlmostEqual(area, total - edge)
        self.assertAlmostEqual(rep.sides[relief.SIDES.index("E")], 1.0)
        self.assertAlmostEqual(rep.median, math.degrees(math.atan(0.2)))

    def test_tile_inside_and_outside(self):
        result = relief.analyse(east_plane(self.grid, 0.2), self.grid, R)
        lats = np.array([[55.0, 56.0]])
        lons = np.array([[37.0, 37.0]])
        rgba = relief.tile_rgba(result, lats, lons, R)
        self.assertGreater(int(rgba[0, 0, 3]), 0)
        self.assertEqual(int(rgba[0, 1, 3]), 0)
        aspect = relief.tile_rgba(result._replace(mode="aspect"),
                                  lats, lons, R)
        self.assertGreater(int(aspect[0, 0, 3]), 0)
        self.assertEqual(int(aspect[0, 1, 3]), 0)

    def test_aspect_outside_area_is_empty(self):
        # Вне участка многоугольником высоты NaN: экспозиция там не
        # «ровное место» цветом, а прозрачна, как уклон.
        z = east_plane(self.grid, 0.2)
        z[:, :self.grid.cols // 2] = np.nan
        result = relief.analyse(z, self.grid, R, mode="aspect")
        lat, lon_w = hydro.latlon(self.grid, 5, 3, R)
        _, lon_e = hydro.latlon(self.grid, 5, self.grid.cols - 4, R)
        lats = np.array([[float(lat), float(lat)]])
        lons = np.array([[float(lon_e), float(lon_w)]])
        rgba = relief.tile_rgba(result, lats, lons, R)
        self.assertGreater(int(rgba[0, 0, 3]), 0)
        self.assertEqual(int(rgba[0, 1, 3]), 0)

    def test_extremes_of_hill(self):
        rows, cols = np.mgrid[0:self.grid.rows, 0:self.grid.cols]
        z = 100.0 + 60.0 * np.exp(-((rows - 50) ** 2 + (cols - 40) ** 2)
                                  / 200.0)
        found = relief.extremes(z, self.grid, radius_m=200.0, drop=10.0)
        peaks = [f for f in found if f[4] == "peak"]
        self.assertEqual(len(peaks), 1)
        self.assertEqual(peaks[0][:2], (50, 40))


if __name__ == "__main__":
    unittest.main()
