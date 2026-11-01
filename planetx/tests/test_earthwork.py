# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Земляные работы: выемка и насыпь до ровной площадки."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import hydro  # noqa: E402
import volumes  # noqa: E402

RADIUS = 6378137.0


def plain(rows=11):
    grid = hydro.make_grid(58.0, 56.0, 50.0 * (rows - 1), 100.0, RADIUS)
    return grid._replace(cell=100.0)


class TestEarthwork(unittest.TestCase):

    def test_hill_above_level_is_cut(self):
        grid = plain()
        z = np.full((grid.rows, grid.cols), 100.0)
        z[5, 5] = 130.0
        work = volumes.earthwork(z, grid, 100.0, RADIUS)
        out = volumes.summary(work.diff, grid.cell ** 2)
        self.assertAlmostEqual(out["cut"], 30.0 * 100.0 ** 2)
        self.assertEqual(out["fill"], 0.0)

    def test_pit_below_level_is_fill(self):
        grid = plain()
        z = np.full((grid.rows, grid.cols), 100.0)
        z[2, 3] = 90.0
        work = volumes.earthwork(z, grid, 100.0, RADIUS)
        out = volumes.summary(work.diff, grid.cell ** 2)
        self.assertAlmostEqual(out["fill"], 10.0 * 100.0 ** 2)
        self.assertEqual(out["cut"], 0.0)

    def test_balance_level_gives_equal_volumes(self):
        grid = plain()
        rows = np.arange(grid.rows, dtype=np.float64)
        z = 100.0 + 3.0 * rows[:, None] + np.zeros((grid.rows, grid.cols))
        z[0, 0] = np.nan
        level = volumes.balance_level(z)
        work = volumes.earthwork(z, grid, level, RADIUS)
        out = volumes.summary(work.diff, grid.cell ** 2, threshold=0.0)
        self.assertAlmostEqual(out["net"], 0.0, places=3)
        self.assertGreater(out["cut"], 0.0)

    def test_no_heights_no_level(self):
        self.assertIsNone(volumes.balance_level(np.full((3, 3), np.nan)))

    def test_outside_area_is_not_counted(self):
        grid = plain()
        z = np.full((grid.rows, grid.cols), 90.0)
        z[:, 5:] = np.nan
        work = volumes.earthwork(z, grid, 100.0, RADIUS)
        out = volumes.summary(work.diff, grid.cell ** 2)
        self.assertAlmostEqual(out["fill"],
                               10.0 * 5 * grid.rows * 100.0 ** 2)


class TestOwnShare(unittest.TestCase):

    def test_share_and_error(self):
        grid = plain()
        z = np.full((grid.rows, grid.cols), 100.0)
        work = volumes.earthwork(z, grid, 100.0, RADIUS)
        half = grid.x0 + (grid.cols // 2 + 0.5) * grid.step
        box = (grid.x0 - 1.0, grid.y0 - 1e6, half, grid.y0 + 1.0)
        share = volumes.own_share(work, [box], RADIUS)
        self.assertAlmostEqual(share, 6.0 / 11.0)
        whole = grid.rows * grid.cols * 100.0 ** 2
        self.assertAlmostEqual(volumes.open_error(work, 0.0),
                               whole * volumes.OPEN_ERROR)
        self.assertEqual(volumes.open_error(work, 1.0), 0.0)
        self.assertEqual(volumes.own_share(work, [], RADIUS), 0.0)


class TestTile(unittest.TestCase):

    def test_colors_follow_sign(self):
        grid = plain()
        z = np.full((grid.rows, grid.cols), 100.0)
        z[2, 5] = 150.0  # выемка
        z[8, 5] = 50.0  # насыпь
        z[5, 8] = np.nan
        work = volumes.earthwork(z, grid, 100.0, RADIUS)
        lats, lons = hydro.latlon(grid, np.array([2.0, 8.0, 5.0, 5.0, 40.0]),
                                  np.array([5.0, 5.0, 8.0, 2.0, 5.0]),
                                  RADIUS)
        rgba = volumes.tile_rgba(work, lats, lons, RADIUS)
        self.assertEqual(tuple(rgba[0, :3]), volumes.CUT_RGB)
        self.assertEqual(tuple(rgba[1, :3]), volumes.FILL_RGB)
        self.assertEqual(rgba[0, 3], volumes.ALPHA)
        self.assertEqual(rgba[2, 3], 0)  # вне участка
        self.assertEqual(rgba[3, 3], 0)  # на отметке площадки
        self.assertEqual(rgba[4, 3], 0)  # за сеткой


if __name__ == "__main__":
    unittest.main()
