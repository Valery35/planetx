# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Батиметрия по промерам: шаг грида, рамка, маска."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import sounding  # noqa: E402


class TestCell(unittest.TestCase):

    def test_nice_step(self):
        self.assertEqual(sounding.nice_step(4.47), 5.0)
        self.assertEqual(sounding.nice_step(2.0), 2.0)
        self.assertEqual(sounding.nice_step(0.3), 0.5)
        self.assertEqual(sounding.nice_step(11.0), 20.0)

    def test_tracks_twenty_meters_apart_give_five_meter_cell(self):
        # Галсы через 20 м, точка через метр, участок 1 × 1 км.
        xs, ys = np.meshgrid(np.arange(0.0, 1000.0, 1.0),
                             np.arange(0.0, 1000.0, 20.0))
        self.assertEqual(sounding.auto_cell(xs.ravel(), ys.ravel()), 5.0)

    def test_long_lake_in_empty_frame(self):
        # Полоса 14 × 2 км по диагонали рамки 14 × 16 км: галсы через
        # 50 м, точка через 5 м. По рамке шаг вышел бы 50 м.
        along = np.arange(0.0, 14000.0, 5.0)
        across = np.arange(0.0, 2000.0, 50.0)
        xs, offsets = np.meshgrid(along, across)
        self.assertEqual(sounding.auto_cell(xs.ravel(),
                                            (xs + offsets).ravel()), 20.0)

    def test_cell_limited_by_grid_size(self):
        xs = np.array([0.0, 1.0e5, 0.0, 1.0e5] * 1000)
        ys = np.array([0.0, 0.0, 1.0e5, 1.0e5] * 1000)
        cell = sounding.auto_cell(xs, ys)
        self.assertLessEqual((1.0e5 / cell) ** 2, sounding.MAX_CELLS)


class TestFrame(unittest.TestCase):

    def test_frame_is_multiple_of_cell_and_covers_points(self):
        (w, s, e, n), (cols, rows) = sounding.grid_frame(
            [3.2, 47.9], [11.0, 18.5], 5.0)
        self.assertEqual((w, s, e, n), (-5.0, 5.0, 55.0, 25.0))
        self.assertEqual((cols, rows), (12, 4))


class TestClean(unittest.TestCase):

    def test_negative_depth_and_nan(self):
        xs, ys, zs = sounding.clean([0, 1, 2], [0, 1, 2],
                                    [-3.0, float("nan"), 4.0])
        self.assertEqual(list(zs), [3.0, 4.0])
        self.assertEqual(list(xs), [0.0, 2.0])

    def test_mask_far_cells(self):
        depths = np.array([[1.0, 2.0], [3.0, sounding.NODATA]])
        distance = np.array([[0.0, 60.0], [10.0, 0.0]])
        out = sounding.masked(depths, distance, 50.0)
        self.assertEqual(out[0, 1], sounding.NODATA)
        self.assertEqual(out[1, 0], 3.0)
        self.assertEqual(out[1, 1], sounding.NODATA)


if __name__ == "__main__":
    unittest.main()
