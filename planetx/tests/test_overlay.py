# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно наложения: своя картинка или часть картинки предка."""
import math
import os
import sys
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import overlay as ov  # noqa: E402
import tiling as tl  # noqa: E402


class TestWindow(unittest.TestCase):

    def test_own_picture(self):
        key = (10, 671, 308)
        self.assertEqual(ov.window(key, lambda k: k == key),
                         (key, (0.0, 0.0, 1.0)))

    def test_nothing_ready(self):
        self.assertIsNone(ov.window((10, 671, 308), lambda k: False))

    def test_too_deep_ancestor_is_not_used(self):
        key = (12, 2684, 1232)
        root = (12 - ov.MAX_ANCESTOR_DEPTH - 1, key[1] >> 7, key[2] >> 7)
        self.assertIsNone(ov.window(key, lambda k: k == root))

    def test_ancestor_window_hits_the_same_ground(self):
        # Угол тайла и его середина в координатах предка лежат в тех же
        # широте и долготе, что в координатах самого тайла.
        for key in ((10, 671, 308), (15, 21503, 9861), (3, 5, 2)):
            for depth in range(0, min(key[0], ov.MAX_ANCESTOR_DEPTH) + 1):
                parent = (key[0] - depth, key[1] >> depth, key[2] >> depth)
                found, (du, dv, s) = ov.window(key, lambda k: k == parent)
                self.assertEqual(found, parent)
                for u, v in ((0, 0), (1, 1), (0.5, 0.25)):
                    self.assertTrue(math.isclose(
                        *[self.lon(*k, uu) for k, uu in
                          ((key, u), (parent, du + s * u))],
                        abs_tol=1e-9))
                    self.assertTrue(math.isclose(
                        *[self.merc(*k, vv) for k, vv in
                          ((key, v), (parent, dv + s * v))],
                        abs_tol=1e-9))

    @staticmethod
    def lon(z, x, y, u):
        return (x + u) / (1 << z) * 360.0 - 180.0

    @staticmethod
    def merc(z, x, y, v):
        # Координата Mercator по вертикали в долях мира, 0 - север.
        return (y + v) / (1 << z)

    def test_parent_bounds_agree_with_tiling(self):
        key = (10, 671, 308)
        parent = (9, 335, 154)
        _, (du, dv, s) = ov.window(key, lambda k: k == parent)
        west = tl.tile_bounds(*key)[0]
        pwest, _, peast, _ = tl.tile_bounds(*parent)
        self.assertAlmostEqual(pwest + du * (peast - pwest), west)
        self.assertEqual(s, 0.5)


class TestMercator(unittest.TestCase):

    def test_bounds_match_tiling(self):
        # Запад и восток тайла в метрах Mercator - те же долготы, что
        # у tiling.tile_bounds. Север и юг - те же широты.
        r = ov.HALF_WORLD
        for key in ((0, 0, 0), (3, 5, 2), (10, 671, 308)):
            west, south, east, north = ov.mercator_bounds(*key)
            lon_w, lat_s, lon_e, lat_n = tl.tile_bounds(*key)
            self.assertAlmostEqual(west / r * 180.0, lon_w, places=9)
            self.assertAlmostEqual(east / r * 180.0, lon_e, places=9)
            for y, lat in ((north, lat_n), (south, lat_s)):
                back = math.degrees(math.atan(math.sinh(y / r * math.pi)))
                self.assertAlmostEqual(back, lat, places=9)

    def test_urgency_order(self):
        key = (12, 2684, 1232)
        none = ov.urgency(key, None)
        far = ov.urgency(key, ((12 - ov.MAX_ANCESTOR_DEPTH,
                                2684 >> ov.MAX_ANCESTOR_DEPTH,
                                1232 >> ov.MAX_ANCESTOR_DEPTH), (0, 0, 1)))
        near = ov.urgency(key, ((11, 1342, 616), (0, 0, 1)))
        self.assertGreater(none, far)
        self.assertGreater(far, near)


if __name__ == "__main__":
    unittest.main()
