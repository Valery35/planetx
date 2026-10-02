# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Уклон и экспозиция по тайлу высот."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import slope as sl  # noqa: E402

R = 6378137.0


def plane(z, y, east, north):
    """Высоты наклонной плоскости: подъём east на метр к востоку
    и north на метр к северу, по настоящему шагу пикселей строки."""
    step = sl.pixel_size(z, y, R)
    cols = np.arange(sl.SIZE) * step[:, None]
    # Строки идут к югу, расстояние к северу - со знаком минус.
    rows = -np.cumsum(np.r_[0.0, step[1:]])[:, None]
    return east * cols + north * rows


class TestSlope(unittest.TestCase):

    def test_plane_rising_east(self):
        # Подъём 1 м на 10 м к востоку: уклон atan(0.1), склон смотрит
        # вниз - на запад, 270°.
        z, y = 14, 5000
        s, a = sl.slope_aspect(plane(z, y, 0.1, 0.0), z, y, R)
        inner = (slice(5, -5), slice(5, -5))
        self.assertAlmostEqual(float(np.mean(s[inner])),
                               math.degrees(math.atan(0.1)), places=2)
        self.assertAlmostEqual(float(np.mean(a[inner])), 270.0, places=1)

    def test_plane_rising_north_faces_south(self):
        z, y = 12, 1300
        s, a = sl.slope_aspect(plane(z, y, 0.0, 1.0), z, y, R)
        inner = (slice(5, -5), slice(5, -5))
        self.assertAlmostEqual(float(np.mean(s[inner])), 45.0, places=1)
        self.assertAlmostEqual(float(np.mean(a[inner])), 180.0, places=1)

    def test_flat_has_no_aspect(self):
        s, a = sl.slope_aspect(np.full((256, 256), 120.0), 10, 300, R)
        self.assertEqual(float(s.max()), 0.0)
        self.assertTrue(np.isnan(a).all())

    def test_pixel_size_shrinks_to_pole(self):
        north = sl.pixel_size(3, 0, R)
        self.assertLess(north[0], north[-1])
        # Тайл уровня 0 у экватора - 40 075 км на 256 пикселей.
        middle = sl.pixel_size(0, 0, R)[128]
        self.assertAlmostEqual(middle, 2 * math.pi * R / 256, delta=200.0)

    def test_colors(self):
        s = np.array([[1.0, 7.0, 40.0]])
        rgba = sl.slope_rgba(s)
        self.assertEqual(rgba.shape, (1, 3, 4))
        self.assertEqual(int(rgba[0, 0, 3]), round(sl.OPACITY * 255))
        # Ровное - зелёное, крутое - лиловое, премноженная альфа.
        self.assertGreater(rgba[0, 0, 1], rgba[0, 0, 0])
        self.assertGreater(rgba[0, 2, 2], rgba[0, 2, 1])
        a = sl.aspect_rgba(np.array([[np.nan, 90.0]]))
        self.assertLess(a[0, 0, 3], a[0, 1, 3])


if __name__ == "__main__":
    unittest.main()
