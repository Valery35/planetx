# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
# Перенесено из Isoliner, grid_isolines/tests/test_topo_flow.py.
# Там - GPL-2.0-or-later, владелец тот же.
"""Тесты гидрологии рельефа: D8, аккумуляция, сеть, бассейны."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import topo_flow as tf  # noqa: E402
from hydro_fill import fill_depressions  # noqa: E402


def _plane_east(ny=8, nx=10):
    """Наклон на восток: сток строго E (код 1)."""
    c = np.arange(nx, dtype=float)
    return np.tile(100.0 - c, (ny, 1))


class TestD8(unittest.TestCase):

    def test_east_plane(self):
        z = _plane_east()
        dir_idx, down = tf.d8_directions(z)
        esri = tf.dir_to_esri(dir_idx)
        # весь грид, кроме восточного края, течёт на восток
        self.assertTrue((esri[:, :-1] == 1).all())
        # восточный край уходит с грида
        self.assertTrue((dir_idx[:, -1] == tf.NODIR).all())
        self.assertTrue((down.reshape(z.shape)[:, -1] == -1).all())

    def test_diagonal_wins(self):
        # уклон по диагонали круче осевого на достаточную величину
        z = np.array([[3.0, 2.0],
                      [2.0, 0.5]])
        dir_idx, _ = tf.d8_directions(z)
        self.assertEqual(tf.dir_to_esri(dir_idx)[0, 0], 2)  # SE

    def test_nodata_is_outlet(self):
        z = _plane_east(4, 4)
        mask = np.zeros_like(z, dtype=bool)
        mask[1, 2] = True
        dir_idx, down = tf.d8_directions(z, nodata_mask=mask)
        self.assertEqual(dir_idx[1, 2], tf.NODIR)
        # западный сосед nodata льёт в неё как в слив: downstream -1
        self.assertEqual(down.reshape(z.shape)[1, 1], -1)

    def test_pit_is_sink(self):
        z = _plane_east(5, 5)
        z[2, 2] = 0.0
        dir_idx, down = tf.d8_directions(z)
        self.assertEqual(dir_idx[2, 2], tf.NODIR)
        self.assertEqual(down.reshape(25)[12], -1)


class TestAccumulation(unittest.TestCase):

    def test_east_plane_rows(self):
        z = _plane_east(3, 6)
        _, down = tf.d8_directions(z)
        acc = tf.flow_accumulation(down, z.shape)
        # вдоль строки аккумуляция растёт 1..nx
        for j in range(6):
            self.assertTrue((acc[:, j] == j + 1).all())

    def test_total_conservation(self):
        rng = np.random.default_rng(7)
        z = rng.random((40, 50)) * 10 + np.arange(50)[None, :] * 0.5
        filled, _, _ = fill_depressions(z, epsilon=1e-3)
        _, down = tf.d8_directions(filled)
        acc = tf.flow_accumulation(down, filled.shape)
        # каждая ячейка считает себя: минимум 1, максимум не больше N
        self.assertGreaterEqual(acc.min(), 1.0)
        self.assertLessEqual(acc.max(), filled.size)
        # сумма аккумуляции устьев равна... не обязана, но каждая
        # ячейка доходит до какого-то устья: проверим через бассейны
        lab = tf.basins(down, filled.shape)
        self.assertTrue((lab > 0).all())

    def test_v_valley_outlet(self):
        # V-долина, падающая на юг: вся вода в одной ячейке выхода
        ny, nx = 20, 11
        col = np.abs(np.arange(nx) - nx // 2).astype(float)
        z = col[None, :] * 2.0 + (ny - np.arange(ny))[:, None] * 0.5
        filled, _, _ = fill_depressions(z, epsilon=1e-4)
        _, down = tf.d8_directions(filled)
        acc = tf.flow_accumulation(down, z.shape)
        self.assertEqual(acc[-1, nx // 2], float(ny * nx))


class TestRiverNetwork(unittest.TestCase):

    def _y_network(self):
        """Два истока сливаются в один ствол (форма Y, падение на юг)."""
        ny, nx = 30, 21
        col = np.abs(np.arange(nx) - nx // 2).astype(float)
        z = col[None, :] * 3.0 + (ny - np.arange(ny))[:, None] * 1.0
        # два боковых оврага в верхней половине
        for r in range(0, 12):
            z[r, 4 + r // 3] -= 2.5
            z[r, 16 - r // 3] -= 2.5
        filled, _, _ = fill_depressions(z, epsilon=1e-4)
        _, down = tf.d8_directions(filled)
        acc = tf.flow_accumulation(down, z.shape)
        return down, acc, z.shape

    def test_strahler_increases(self):
        down, acc, shape = self._y_network()
        links = tf.river_network(down, acc, threshold=8, shape=shape)
        self.assertGreater(len(links), 1)
        orders = [lk["order"] for lk in links]
        self.assertEqual(min(orders), 1)
        self.assertGreaterEqual(max(orders), 2)
        # звенья направлены вниз по течению: аккумуляция не убывает
        flat_acc = acc.ravel()
        for lk in links:
            cells = lk["cells"]
            self.assertGreater(len(cells), 1)
            self.assertLessEqual(flat_acc[cells[0]],
                                 flat_acc[cells[-1]] + 1e-9)

    def test_threshold_prunes(self):
        down, acc, shape = self._y_network()
        many = tf.river_network(down, acc, threshold=5, shape=shape)
        few = tf.river_network(down, acc, threshold=100, shape=shape)
        n_many = sum(len(lk["cells"]) for lk in many)
        n_few = sum(len(lk["cells"]) for lk in few)
        self.assertGreater(n_many, n_few)


class TestBasins(unittest.TestCase):

    def test_ridge_splits_two(self):
        # хребет по центру: западная половина льёт на запад, восточная
        # на восток, автоматические устья по краю
        ny, nx = 10, 21
        col = -np.abs(np.arange(nx) - nx // 2).astype(float)
        z = np.tile(col * 2.0 + 100.0, (ny, 1))
        z += np.arange(ny)[:, None] * 1e-6  # лёгкий наклон против плоскостей
        filled, _, _ = fill_depressions(z, epsilon=1e-6)
        _, down = tf.d8_directions(filled)
        acc = tf.flow_accumulation(down, z.shape)
        lab = tf.basins(down, z.shape, acc=acc, threshold=acc.max() * 0.4)
        got = set(np.unique(lab)) - {0}
        self.assertGreaterEqual(len(got), 2)

    def test_seed_catches_upstream(self):
        z = _plane_east(6, 12)
        _, down = tf.d8_directions(z)
        # семя в середине строки 2: всё западнее в его бассейне
        seed_flat = 2 * 12 + 6
        lab = tf.basins(down, z.shape, seeds={seed_flat: 5})
        self.assertEqual(lab[2, 6], 5)
        self.assertTrue((lab[2, :6] == 5).all())
        self.assertTrue((lab[3, :] != 5).all())
        # восточнее семени вода уже прошла: метки нет
        self.assertTrue((lab[2, 7:] == 0).all())

    def test_pointer_doubling_long_chain(self):
        # длинная цепочка из 5000 ячеек в одну сторону
        z = _plane_east(1, 5000)
        _, down = tf.d8_directions(z)
        lab = tf.basins(down, z.shape)
        self.assertTrue((lab == lab[0, -1]).all())
        self.assertGreater(lab[0, 0], 0)


if __name__ == "__main__":
    unittest.main()
