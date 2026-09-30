# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Вид неба: оси, проекция, перетаскивание, угол обзора."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import skyview as sv  # noqa: E402
from stars import sky_directions  # noqa: E402


class TestSkyView(unittest.TestCase):

    def test_axes_are_orthonormal(self):
        view = sv.SkyView(123.0, -40.0, 60.0)
        r = view.rotation()
        self.assertTrue(np.allclose(r.T @ r, np.eye(3)))
        self.assertAlmostEqual(np.linalg.det(r), 1.0)

    def test_centre_and_north_up(self):
        view = sv.SkyView(83.0, 5.0, 40.0)
        centre = sky_directions([math.radians(83.0)], [math.radians(5.0)])
        (x, y), = view.project(centre, 1600, 900)[0]
        self.assertAlmostEqual(x, 800.0, places=6)
        self.assertAlmostEqual(y, 450.0, places=6)
        north = sky_directions([math.radians(83.0)], [math.radians(15.0)])
        east = sky_directions([math.radians(93.0)], [math.radians(5.0)])
        (nx, ny), = view.project(north, 1600, 900)[0]
        (ex, ey), = view.project(east, 1600, 900)[0]
        self.assertLess(ny, 450.0)  # север выше середины
        self.assertLess(ex, 800.0)  # восток слева, изнутри сферы

    def test_behind_is_masked(self):
        view = sv.SkyView(0.0, 0.0, 60.0)
        back = sky_directions([math.pi], [0.0])
        self.assertFalse(view.project(back, 800, 600)[1][0])

    def test_pixel_round_trip(self):
        view = sv.SkyView(250.0, 60.0, 80.0)
        v = view.direction_at(300.0, 200.0, 1200, 800)
        (x, y), = view.project(v[None], 1200, 800)[0]
        self.assertAlmostEqual(x, 300.0, places=6)
        self.assertAlmostEqual(y, 200.0, places=6)

    def test_drag_follows_cursor(self):
        # Точка под курсором после перетаскивания уходит вместе с ним.
        view = sv.SkyView(40.0, 20.0, 30.0)
        v = view.direction_at(600.0, 400.0, 1200, 800)
        view.drag(50.0, -30.0, 800)
        (x, y), = view.project(v[None], 1200, 800)[0]
        self.assertAlmostEqual(x, 650.0, delta=1.5)
        self.assertAlmostEqual(y, 370.0, delta=1.5)

    def test_limits(self):
        view = sv.SkyView(0.0, 0.0, 60.0)
        view.zoom(1e-3)
        self.assertEqual(view.fov, sv.FOV_MIN)
        view.zoom(1e6)
        self.assertEqual(view.fov, sv.FOV_MAX)
        view.drag(0.0, 1e7, 800)
        self.assertAlmostEqual(view.dec, sv.DEC_LIMIT)


if __name__ == "__main__":
    unittest.main()
