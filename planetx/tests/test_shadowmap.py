# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Матрицы карты теней кадра."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid as el  # noqa: E402
import shadowmap as sm  # noqa: E402


def enu(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    east = np.array([-math.sin(lo), math.cos(lo), 0.0])
    north = np.array([-math.sin(la) * math.cos(lo),
                      -math.sin(la) * math.sin(lo), math.cos(la)])
    up = np.array([math.cos(la) * math.cos(lo),
                   math.cos(la) * math.sin(lo), math.sin(la)])
    return east, north, up


LAT, LON = 43.35, 42.45
CENTER = np.ravel(el.geodetic_to_ecef(np.array([LAT]), np.array([LON]),
                                      np.array([2000.0])))
EAST, NORTH, UP = enu(LAT, LON)
SUN = math.cos(math.radians(20.0)) * NORTH + math.sin(math.radians(20.0)) * UP


class TestShadowMap(unittest.TestCase):

    def test_radius_steps_and_limits(self):
        self.assertIsNone(sm.radius_for(sm.FROM * 2))
        self.assertEqual(sm.radius_for(10.0), sm.radius_for(100.0))
        self.assertLessEqual(sm.radius_for(30000.0), sm.REACH)
        # Небольшой сдвиг расстояния не меняет радиус.
        self.assertEqual(sm.radius_for(1000.0), sm.radius_for(1001.0))

    def test_center_maps_to_middle_and_sun_side_is_nearer(self):
        frame = sm.LightFrame(CENTER, SUN, 1000.0)
        self.assertTrue(frame.active)
        middle = frame.project(CENTER)
        self.assertLess(abs(middle[0]), 2.0 / frame.size)
        self.assertLess(abs(middle[1]), 2.0 / frame.size)
        # Точка над центром ближе к солнцу - глубина меньше.
        above = frame.project(CENTER + 100.0 * UP)
        self.assertLess(above[2], middle[2])
        # Точка на востоке на 900 м - у края квадрата по x.
        east = frame.project(CENTER + 900.0 * EAST)
        self.assertAlmostEqual(abs(east[0] - middle[0]), 0.9, delta=0.01)

    def test_matrices_match_projection(self):
        frame = sm.LightFrame(CENTER, SUN, 2000.0)
        centers = np.array([CENTER + 300.0 * EAST, CENTER - 700.0 * NORTH])
        mats = frame.matrices(centers)
        offset = np.array([12.0, -5.0, 40.0])
        for mat, c in zip(mats, centers):
            got = mat @ np.append(offset, 1.0)
            want = frame.project(c + offset)
            np.testing.assert_allclose(got[:3], want, atol=1e-9)

    def test_float32_matrices_keep_precision(self):
        # Матрица - в float32, как в видеокарте: ошибка меньше тексела.
        frame = sm.LightFrame(CENTER, SUN, 1000.0)
        tile = CENTER + 1500.0 * NORTH
        mat = sm.LightCamera(frame).tiles_mvp([tile])[0].astype(np.float64)
        offset = np.array([30.0, 20.0, -10.0])
        got = mat @ np.append(offset, 1.0)
        want = frame.project(tile + offset)
        self.assertLess(np.max(np.abs(got[:3] - want)[:2]) * frame.size / 2,
                        0.01)

    def test_snapped_center_moves_by_texels(self):
        a = sm.LightFrame(CENTER, SUN, 1000.0)
        b = sm.LightFrame(CENTER + 1.3 * EAST, SUN, 1000.0)
        shift = b.project(a.center)[:2] * a.size / 2.0
        np.testing.assert_allclose(shift, np.round(shift), atol=1e-6)

    def test_sun_below_horizon_is_inactive(self):
        frame = sm.LightFrame(CENTER, -SUN, 1000.0)
        self.assertFalse(frame.active)


if __name__ == "__main__":
    unittest.main()
