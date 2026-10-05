# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Врезка своего рельефа: рамки тайлов, уровень, край, слияние,
глубокие уровни хранилища высот."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import inset  # noqa: E402
import terrain as tr  # noqa: E402


def flat_tile(z, x, y, height):
    heights = np.full((tr.SIZE, tr.SIZE), height, dtype=np.float32)
    return tr.HeightTile(z, x, y, heights, height, height)


class TestGeometry(unittest.TestCase):

    def test_tile_bounds_cover_world(self):
        west, south, east, north = inset.tile_bounds(0, 0, 0)
        self.assertAlmostEqual(west, -inset.HALF)
        self.assertAlmostEqual(north, inset.HALF)
        self.assertAlmostEqual(east - west, 2.0 * inset.HALF)
        u0, v0, u1, v1 = inset.shares(*inset.tile_bounds(3, 5, 2))
        self.assertAlmostEqual(u0, 5 / 8.0)
        self.assertAlmostEqual(v0, 2 / 8.0)
        self.assertAlmostEqual(u1, 6 / 8.0)
        self.assertAlmostEqual(v1, 3 / 8.0)

    def test_level_follows_pixel(self):
        # Пиксель уровня 15 в метрах EPSG:3857 - около 4.8 м.
        pixel15 = 2.0 * inset.HALF / (256 * 2 ** 15)
        self.assertEqual(inset.level_for(pixel15), 15)
        self.assertEqual(inset.level_for(pixel15 / 2.0), 16)
        self.assertEqual(inset.level_for(1.0), tr.DEEP_LEVEL)
        self.assertEqual(inset.level_for(30.0), tr.MAX_LEVEL)
        self.assertEqual(inset.level_for(0.01), tr.DEEP_LEVEL)


class TestMerge(unittest.TestCase):

    def test_edge_weight_is_smooth(self):
        w = inset.edge_weight(np.array([0.0, 25.0, 50.0, 100.0, 300.0]),
                              100.0)
        self.assertEqual(w[0], 0.0)
        self.assertAlmostEqual(float(w[2]), 0.5)
        self.assertEqual(w[3], 1.0)
        self.assertEqual(w[4], 1.0)
        self.assertTrue(np.all(np.diff(w) >= 0.0))

    def test_merge_replaces_inside_and_keeps_nodata(self):
        base = np.full((4, 4), 100.0, dtype=np.float32)
        dem = np.full((4, 4), 40.0, dtype=np.float32)
        dem[0, 0] = np.nan
        weight = np.ones((4, 4), dtype=np.float32)
        weight[1, 1] = 0.5
        weight[2, 2] = np.nan
        out = inset.merge(base, dem, weight)
        self.assertEqual(out[3, 3], 40.0)
        self.assertEqual(out[0, 0], 100.0)  # без данных - Terrarium
        self.assertEqual(out[1, 1], 70.0)  # полоса края
        self.assertEqual(out[2, 2], 100.0)
        self.assertEqual(out.dtype, np.float32)

    def test_band_is_share_of_smaller_side(self):
        self.assertAlmostEqual(inset.band_width(0.0, 0.0, 4000.0, 2000.0),
                               100.0)


class TestDeepStore(unittest.TestCase):

    def test_cap_and_wanted_inside_box(self):
        store = tr.HeightStore()
        box = inset.shares(*inset.tile_bounds(16, 40000, 20000))
        store.deep = [box + (17,)]
        inside = (19, 40000 * 8 + 3, 20000 * 8 + 3)
        outside = (19, 1000, 1000)
        self.assertEqual(store.cap(inside), 17)
        self.assertEqual(store.cap(outside), tr.MAX_LEVEL)
        self.assertEqual(store.wanted(inside)[0], 17)
        self.assertEqual(store.wanted(outside)[0], tr.MAX_LEVEL)

    def test_deep_tile_is_used(self):
        store = tr.HeightStore()
        key = (17, 80000, 40000)
        store.deep = [inset.shares(*inset.tile_bounds(*key)) + (17,)]
        store.add(flat_tile(15, 80000 >> 2, 40000 >> 2, 10.0))
        store.add(flat_tile(*key, 55.0))
        self.assertEqual(store.best((19, 80000 * 4 + 1, 40000 * 4 + 1)).z,
                         17)
        u = (80000 + 0.5) / 2 ** 17
        v = (40000 + 0.5) / 2 ** 17
        lat = np.degrees(np.arctan(np.sinh(np.pi * (1.0 - 2.0 * v))))
        lon = u * 360.0 - 180.0
        self.assertAlmostEqual(store.height_at(lat, lon), 55.0, places=3)
        self.assertAlmostEqual(float(store.heights_at([lat], [lon])[0]),
                               55.0, places=3)

    def test_resample_from_ancestor(self):
        heights = np.tile(np.arange(tr.SIZE, dtype=np.float32), (tr.SIZE, 1))
        parent = tr.HeightTile(15, 100, 200, heights, 0.0, 255.0)
        child = tr.resample(parent, (16, 201, 400))
        self.assertEqual(child.shape, (tr.SIZE, tr.SIZE))
        # Правая половина предка: столбцы 128-255.
        self.assertAlmostEqual(float(child[0, 0]), 127.75, places=3)
        self.assertAlmostEqual(float(child[0, -1]), 255.0, places=3)

    def test_flat_level_is_deeper_than_any(self):
        self.assertGreater(tr.FLAT_LEVEL, tr.DEEP_LEVEL)


if __name__ == "__main__":
    unittest.main()
