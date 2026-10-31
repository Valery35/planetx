# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты классификации по своему растру (core/rasterclass.py)."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import rasterclass  # noqa: E402

SIDE = 60


def scene(seed=7):
    """Растр с известными классами: левая половина и правая. Канал 0 -
    высота в метрах с большим шумом, не связанным с классом, канал 1 -
    отражение в долях единицы, класс только в нём."""
    random = np.random.default_rng(seed)
    truth = np.zeros((SIDE, SIDE), dtype=np.int16)
    truth[:, SIDE // 2:] = 1
    height = 2000.0 + 3.0 * random.normal(size=truth.shape)
    light = np.where(truth == 0, 0.1, 0.4) \
        + 0.01 * random.normal(size=truth.shape)
    return np.stack([height, light]).astype(np.float32), truth


def points(grid, cells):
    return grid[:, [c[0] for c in cells], [c[1] for c in cells]]


LEFT = [(10, 10), (30, 12), (50, 8)]
RIGHT = [(10, 50), (30, 48), (50, 52)]


class TestClassify(unittest.TestCase):

    def run_scene(self, grid, **options):
        samples = points(grid, LEFT + RIGHT)
        return rasterclass.classify(grid, samples, [0, 0, 0, 1, 1, 1],
                                    **options)

    def test_channels_in_different_units(self):
        # Каналы приведены к разбросу 1: отражение решает, хотя метры
        # больше его на четыре порядка. Без приведения красный.
        grid, truth = scene()
        classes, _ = self.run_scene(grid)
        self.assertEqual(int((classes == truth).sum()), SIDE * SIDE)

    def test_single_band(self):
        # На одном канале у косинуса все клетки одинаковы.
        grid, truth = scene()
        classes, _ = self.run_scene(grid[1:])
        self.assertEqual(int((classes == truth).sum()), SIDE * SIDE)

    def test_large_offset_in_float32(self):
        # Координаты и абсолютные отметки: квадрат расстояния считается
        # по приведённым каналам, большое среднее не съедает точность.
        grid, truth = scene()
        grid[0] = grid[0] + 1.0e6
        classes, _ = self.run_scene(grid)
        self.assertEqual(int((classes == truth).sum()), SIDE * SIDE)

    def test_control_point_cell_is_own_class(self):
        grid, _ = scene()
        classes, distance = self.run_scene(grid)
        for label, cells in enumerate((LEFT, RIGHT)):
            for row, col in cells:
                self.assertEqual(int(classes[row, col]), label)
                self.assertLess(float(distance[row, col]), 1e-2)

    def test_no_data_and_outside_have_no_class(self):
        grid, truth = scene()
        grid[1, 20:25, 20:25] = np.nan  # дыра одного канала
        inside = np.ones(truth.shape, dtype=bool)
        inside[:5] = False
        classes, distance = self.run_scene(grid, inside=inside)
        self.assertTrue((classes[20:25, 20:25] == -1).all())
        self.assertTrue((classes[:5] == -1).all())
        self.assertTrue(np.isnan(distance[:5]).all())
        hit = classes >= 0
        self.assertEqual(int((classes[hit] == truth[hit]).sum()),
                         SIDE * SIDE - 25 - 5 * SIDE)

    def test_point_without_data_does_not_vote(self):
        grid, _ = scene()
        samples = points(grid, LEFT + RIGHT)
        labels = [5, 5, 5, 9, 9, 9]
        without, _ = rasterclass.classify(grid, samples[:, 1:], labels[1:])
        samples[1, 0] = np.nan
        classes, _ = rasterclass.classify(grid, samples, labels)
        self.assertEqual(sorted(np.unique(classes).tolist()), [5, 9])
        self.assertTrue((classes == without).all())

    def test_unequal_classes(self):
        # Две точки против трёх при шумном канале: без деления голосов
        # на количество точек класс с тремя точками забирал 6 % клеток.
        grid, truth = scene()
        samples = points(grid, LEFT[1:] + RIGHT)
        classes, _ = rasterclass.classify(grid, samples, [0, 0, 1, 1, 1])
        self.assertGreater(float((classes == truth).mean()), 0.99)

    def test_constant_channel_is_not_a_feature(self):
        grid, truth = scene()
        grid = np.concatenate([grid, np.full((1,) + truth.shape, 7.0,
                                             dtype=np.float32)])
        classes, _ = self.run_scene(grid)
        self.assertEqual(int((classes == truth).sum()), SIDE * SIDE)
        mean, spread = rasterclass.scales(grid)
        self.assertEqual(float(spread[2]), 0.0)
        self.assertAlmostEqual(float(mean[2]), 7.0)

    def test_nothing_to_compare(self):
        grid = np.full((2, 4, 4), 3.0, dtype=np.float32)
        classes, _ = rasterclass.classify(grid, grid[:, :2, 0], [0, 1])
        self.assertTrue((classes == -1).all())
        empty = np.full((1, 3, 3), np.nan, dtype=np.float32)
        classes, _ = rasterclass.classify(empty, np.ones((1, 2)), [0, 1])
        self.assertTrue((classes == -1).all())

    def test_parts_equal_whole(self):
        grid, _ = scene()
        whole, _ = self.run_scene(grid)
        saved, rasterclass.CHUNK = rasterclass.CHUNK, 97
        seen = []
        try:
            parts, _ = self.run_scene(
                grid, progress=lambda done, total: seen.append(done))
        finally:
            rasterclass.CHUNK = saved
        self.assertTrue((parts == whole).all())
        self.assertEqual(seen[:2], [0, 97])


class TestSize(unittest.TestCase):

    def test_auto_pixel(self):
        self.assertEqual(rasterclass.auto_pixel(10.0, 3000.0), 10.0)
        self.assertEqual(rasterclass.auto_pixel(0.05, 8000.0), 10.0)

    def test_too_big(self):
        self.assertFalse(rasterclass.too_big(1000, 1000, 64))
        self.assertTrue(rasterclass.too_big(1000, 1000, 400))

    def test_covered(self):
        grid = np.ones((2, 2, 2), dtype=np.float32)
        grid[1, 0, 0] = np.nan
        inside = np.array([[True, True], [True, False]])
        self.assertAlmostEqual(rasterclass.covered(grid, inside), 2.0 / 3.0)


if __name__ == "__main__":
    unittest.main()
