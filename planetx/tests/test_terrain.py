# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Высоты Terrarium."""
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import terrain as tr  # noqa: E402
import tiling as tl  # noqa: E402


def encode(heights):
    """Высоты в картинку Terrarium, обратное decode."""
    value = np.asarray(heights, dtype=np.float64) + 32768.0
    r = np.floor(value / 256.0)
    g = np.floor(value - r * 256.0)
    b = np.round((value - r * 256.0 - g) * 256.0)
    rgba = np.stack([r, g, b, np.full_like(r, 255)], axis=-1)
    return rgba.astype(np.uint8)


def ramp_tile(z, x, y):
    """Тайл, высота которого растёт на восток на 10 м за пиксель."""
    cols = np.arange(tr.SIZE, dtype=np.float64) * 10.0
    heights = np.tile(cols, (tr.SIZE, 1))
    return tr.make_tile(z, x, y, encode(heights))


class TestDecode(unittest.TestCase):

    def test_known_values(self):
        values = np.array([[0.0, 5642.0, 123.5, 8848.0]])
        self.assertTrue(np.allclose(tr.decode(encode(values)), values,
                                    atol=1 / 256))

    def test_sea_floor_is_sea_level(self):
        heights = tr.decode(encode(np.array([[-4000.0, -28.0, 10.0]])))
        self.assertEqual(heights.tolist(), [[0.0, 0.0, 10.0]])

    def test_tile_range(self):
        tile = ramp_tile(3, 1, 2)
        self.assertEqual((tile.low, tile.high), (0.0, 2550.0))


class TestSample(unittest.TestCase):

    def test_pixel_centres(self):
        tile = ramp_tile(0, 0, 0)
        for col in (0, 10, 200):
            u = (col + 0.5) / tr.SIZE
            self.assertAlmostEqual(float(tr.sample(tile, u, 0.5)),
                                   col * 10.0, places=6)

    def test_between_centres_is_linear(self):
        tile = ramp_tile(0, 0, 0)
        u = (10.5 + 0.25) / tr.SIZE
        self.assertAlmostEqual(float(tr.sample(tile, u, 0.3)), 102.5,
                               places=6)

    def test_outside_is_clamped(self):
        tile = ramp_tile(4, 5, 6)
        west = 5 / 16 - 0.001
        self.assertAlmostEqual(float(tr.sample(tile, west, 6.5 / 16)), 0.0)

    def test_child_tile_nodes_agree_with_parent_samples(self):
        tile = ramp_tile(5, 10, 12)
        u, v = tr.grid_shares(8, 80, 96, 16)
        direct = tr.sample(tile, u, v)
        # Узлы тайла уровня 8 лежат внутри тайла высот уровня 5.
        self.assertEqual(direct.shape, (17, 17))
        self.assertTrue(np.all(np.diff(direct, axis=1) >= 0))

    def test_neighbours_share_edge_heights(self):
        tile = ramp_tile(6, 20, 20)
        u1, v1 = tr.grid_shares(9, 160, 161, 16)
        u2, v2 = tr.grid_shares(9, 161, 161, 16)
        east = tr.sample(tile, u1, v1)[:, -1]
        west = tr.sample(tile, u2, v2)[:, 0]
        self.assertTrue(np.array_equal(east, west))

    def test_grid_shares_match_tiling(self):
        u, v = tr.grid_shares(7, 88, 38, 16)
        lat, lon = tl.grid_latlon(7, 88, 38)
        self.assertLess(np.abs(u * 360.0 - 180.0 - lon).max(), 1e-9)
        self.assertLess(np.abs(tl.lat_of_row(v) - lat).max(), 1e-9)


class TestStore(unittest.TestCase):

    def test_levels(self):
        self.assertEqual([tr.height_level(z) for z in (0, 2, 3, 10, 17, 19)],
                         [0, 0, 1, 8, 15, 15])

    def test_best_walks_up(self):
        store = tr.HeightStore()
        self.assertIsNone(store.best((10, 600, 300)))
        store.add(ramp_tile(0, 0, 0))
        self.assertEqual(store.best((10, 600, 300)).z, 0)
        store.add(ramp_tile(4, 600 >> 6, 300 >> 6))
        self.assertEqual(store.best((10, 600, 300)).z, 4)
        self.assertEqual(store.wanted((10, 600, 300)), (8, 150, 75))

    def test_height_at_uses_finest(self):
        store = tr.HeightStore()
        store.add(tr.make_tile(0, 0, 0, encode(np.zeros((256, 256)))))
        u, v = tr.mercator_share(43.3499, 42.4453)
        key = (10, int(u * 1024), int(v * 1024))
        store.add(tr.make_tile(*key, encode(np.full((256, 256), 5642.0))))
        self.assertAlmostEqual(store.height_at(43.3499, 42.4453), 5642.0,
                               places=3)
        self.assertEqual(store.height_at(0.0, 0.0), 0.0)

    def test_range_for_uses_the_covered_block(self):
        store = tr.HeightStore()
        self.assertEqual(store.range_for((12, 1, 1)), (0.0, 0.0))
        store.add(ramp_tile(0, 0, 0))
        # Тайл 0 целиком.
        self.assertEqual(store.range_for((0, 0, 0)), (0.0, 2550.0))
        # Правая половина: столбцы 128-255 и ещё один слева на выборку.
        self.assertEqual(store.range_for((1, 1, 0)), (1270.0, 2550.0))
        # Мельче пикселя: пиксель 0 и сосед справа.
        self.assertEqual(store.range_for((12, 1, 1)), (0.0, 10.0))

    def test_range_follows_finer_heights_without_full_reset(self):
        store = tr.HeightStore()
        store.add(ramp_tile(0, 0, 0))
        key = (12, 1, 1)
        far = (12, 3000, 3000)
        self.assertEqual(store.range_for(key), (0.0, 10.0))
        far_range = store.range_for(far)
        cached = store._ranges[far][1]
        # Тайл высот в другом месте не трогает посчитанный размах.
        store.add(tr.make_tile(8, 180, 180,
                               encode(np.full((256, 256), 700.0))))
        self.assertIs(store._ranges[far][1], cached)
        self.assertEqual(store.range_for(far), far_range)
        # Тайл высот точнее над key меняет его размах.
        store.add(tr.make_tile(4, 0, 0, encode(np.full((256, 256), 50.0))))
        self.assertEqual(store.range_for(key), (50.0, 50.0))

    def test_range_is_never_narrower_than_the_mesh(self):
        # Узлы сетки тайла лежат внутри размаха, иначе сфера тайла
        # не накрыла бы его вершины.
        store = tr.HeightStore()
        rng = np.random.default_rng(5)
        tile = tr.make_tile(3, 4, 2, encode(rng.uniform(0, 4000,
                                                        (256, 256))))
        store.add(tile)
        for key in ((5, 17, 9), (7, 70, 38), (9, 280, 150)):
            low, high = store.range_for(key)
            u, v = tr.grid_shares(*key, 16)
            nodes = tr.sample(tile, u, v)
            self.assertGreaterEqual(nodes.min(), low - 1e-6)
            self.assertLessEqual(nodes.max(), high + 1e-6)


class TestHeightsAt(unittest.TestCase):

    def test_matches_single_points(self):
        store = tr.HeightStore()
        store.add(ramp_tile(0, 0, 0))
        store.add(ramp_tile(3, 5, 2))
        store.add(ramp_tile(6, 42, 18))
        rng = np.random.default_rng(3)
        lats = np.concatenate([rng.uniform(-80, 80, 300),
                               rng.uniform(56.5, 58.5, 300)])
        lons = np.concatenate([rng.uniform(-179, 179, 300),
                               rng.uniform(55.0, 57.5, 300)])
        many = store.heights_at(lats, lons)
        one = [store.height_at(a, b) for a, b in zip(lats, lons)]
        self.assertLess(np.abs(many - np.array(one)).max(), 1e-6)

    def test_flat_and_empty(self):
        store = tr.HeightStore()
        store.add(ramp_tile(0, 0, 0))
        store.set_scale(0.0)
        self.assertEqual(store.heights_at([10.0], [20.0]).tolist(), [0.0])
        self.assertEqual(len(tr.HeightStore().heights_at([], [])), 0)


class TestScale(unittest.TestCase):
    """Вертикальный масштаб рельефа и выключенный рельеф."""

    def setUp(self):
        self.store = tr.HeightStore()
        self.tile = tr.make_tile(3, 4, 2, encode(
            np.random.default_rng(7).uniform(0, 4000, (256, 256))))
        self.store.add(self.tile)
        self.key = (7, 70, 38)
        self.lat, self.lon = 50.0, 20.0

    def test_heights_and_ranges_follow_scale(self):
        height = self.store.height_at(self.lat, self.lon)
        low, high = self.store.range_for(self.key)
        self.assertGreater(height, 0.0)
        self.store.set_scale(2.5)
        self.assertAlmostEqual(self.store.height_at(self.lat, self.lon),
                               2.5 * height, places=6)
        self.assertEqual(self.store.range_for(self.key),
                         (2.5 * low, 2.5 * high))

    def test_scaled_range_covers_scaled_mesh(self):
        # Сфера тайла строится по размаху, вершины сетки с тем же
        # масштабом обязаны лежать внутри него.
        self.store.set_scale(4.0)
        low, high = self.store.range_for(self.key)
        mesh = tl.tile_mesh(*self.key, self.tile, exaggeration=4.0)
        seg = mesh.segments
        grid = (mesh.positions[:(seg + 1) ** 2].astype(np.float64)
                + mesh.center)
        lat, lon = tl.grid_latlon(*self.key)
        flat = tl.geodetic_to_ecef(lat, lon, 0.0).reshape(-1, 3)
        up = tl.surface_normal(lat, lon).reshape(-1, 3)
        heights = ((grid - flat) * up).sum(axis=1)
        self.assertGreaterEqual(heights.min(), low - 1.0)
        self.assertLessEqual(heights.max(), high + 1.0)
        self.assertGreater(heights.max(), 3.0 * self.tile.high / 4.0)

    def test_scale_changes_version(self):
        version = self.store.version
        self.store.set_scale(2.0)
        self.assertGreater(self.store.version, version)

    def test_off_means_smooth_earth(self):
        self.store.set_scale(0.0)
        self.assertEqual(self.store.height_at(self.lat, self.lon), 0.0)
        self.assertEqual(self.store.range_for(self.key), (0.0, 0.0))
        self.assertEqual(self.store.for_mesh(self.key),
                         (None, tr.FLAT_LEVEL))

    def test_for_mesh(self):
        self.assertEqual(tr.HeightStore().for_mesh(self.key), (None, -1))
        tile, level = self.store.for_mesh(self.key)
        self.assertIs(tile, self.tile)
        self.assertEqual(level, 3)
        # Сетка без рельефа не пересобирается ни от каких высот.
        self.assertGreater(tr.FLAT_LEVEL, tr.MAX_LEVEL)


if __name__ == "__main__":
    unittest.main()
