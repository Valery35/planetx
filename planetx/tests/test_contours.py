# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Горизонтали тайла и изолинии сетки."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import contours as ct  # noqa: E402

R = 6378137.0


class TestStep(unittest.TestCase):

    def test_nice_series(self):
        self.assertEqual(ct.nice(4.9), 5.0)
        self.assertEqual(ct.nice(21.0), 20.0)
        self.assertEqual(ct.nice(2.3), 2.5)
        self.assertEqual(ct.nice(8.0), 10.0)

    def test_tile_step_by_level(self):
        # Тайлы у Перми, 58° с. ш.: уровень 15 - 5 м, 13 - 20 м.
        y15 = int((1 - np.arcsinh(np.tan(np.radians(58.0))) / np.pi) / 2
                  * (1 << 15))
        self.assertEqual(ct.tile_step(15, y15, R), 5.0)
        self.assertEqual(ct.tile_step(13, y15 >> 2, R), 20.0)


class TestTile(unittest.TestCase):

    def test_lines_on_slope_plane(self):
        # Плоскость, высота растёт на 1 м за пиксель вдоль столбцов:
        # горизонтали через 10 м - вертикальные полосы через 10 пикселей.
        h = np.tile(np.arange(256, dtype=np.float64), (256, 1))
        rgba = ct.contour_rgba(h, 15, 10000, R, step=10.0)
        alpha = rgba[128, :, 3]
        on = np.flatnonzero(alpha > 100)
        self.assertTrue(set(range(10, 250, 10)) <= set(on.tolist()))
        self.assertEqual(alpha[15], 0)
        # Утолщённая горизонталь (50 м) шире обычной (40 м).
        width = lambda c: int(rgba[128, c - 3:c + 4, 3].astype(int).sum())
        self.assertGreater(width(50), width(40))

    def test_water_color_below_zero(self):
        h = np.tile(np.arange(-128, 128, dtype=np.float64), (256, 1))
        rgba = ct.contour_rgba(h, 15, 10000, R, step=10.0)
        under, over = rgba[100, 118], rgba[100, 148]
        self.assertGreater(under[2], under[0])
        self.assertGreater(over[0], over[2])


class TestSegments(unittest.TestCase):

    def test_cone_levels(self):
        r, c = np.mgrid[0:21, 0:21].astype(np.float64)
        z = 100.0 - np.hypot(r - 10, c - 10) * 5.0
        segs = ct.segments(z, 77.0)
        self.assertGreater(len(segs), 10)
        # Точки отрезков - на окружности радиуса 4.6 узла.
        d = np.hypot(segs[..., 0] - 10, segs[..., 1] - 10)
        self.assertTrue(np.allclose(d, 4.6, atol=0.3))

    def test_nan_cells_skipped(self):
        z = np.array([[0.0, 10.0], [0.0, np.nan]])
        self.assertEqual(len(ct.segments(z, 5.0)), 0)

    def test_grid_step_and_levels(self):
        z = np.array([[-306.0, 69.0], [np.nan, 0.0]])
        step = ct.grid_step(z)
        self.assertEqual(step, 25.0)
        lv = ct.levels(z, step)
        self.assertEqual((lv[0], lv[-1]), (-300.0, 50.0))


if __name__ == "__main__":
    unittest.main()
