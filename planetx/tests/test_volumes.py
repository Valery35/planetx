# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Выемка и насыпь между двумя съёмками."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import volumes  # noqa: E402


class TestVolumes(unittest.TestCase):

    def setUp(self):
        self.old = np.full((10, 10), 100.0)
        self.new = self.old.copy()
        self.new[:2, :2] -= 15.0  # выемка 4 ячейки по 15 м
        self.new[5:8, 5:8] += 20.0  # отвал 9 ячеек по 20 м
        self.new[9, 9] += 0.05  # шум съёмки

    def test_cut_fill_net(self):
        diff = volumes.difference(self.old, self.new)
        out = volumes.summary(diff, cell_area=4.0)
        self.assertAlmostEqual(out["cut"], 4 * 15.0 * 4.0)
        self.assertAlmostEqual(out["fill"], 9 * 20.0 * 4.0)
        self.assertAlmostEqual(out["net"], 720.0 - 240.0)
        self.assertAlmostEqual(out["cut_area"], 16.0)
        self.assertAlmostEqual(out["deepest"], -15.0)
        self.assertAlmostEqual(out["highest"], 20.0)
        self.assertAlmostEqual(out["area"], 400.0)

    def test_mask_and_missing(self):
        inside = np.zeros((10, 10), dtype=bool)
        inside[:5, :5] = True
        old = self.old.copy()
        old[0, 0] = np.nan
        out = volumes.summary(volumes.difference(old, self.new, inside),
                              cell_area=1.0)
        self.assertAlmostEqual(out["cut"], 3 * 15.0)
        self.assertEqual(out["fill"], 0.0)
        self.assertAlmostEqual(out["area"], 24.0)

    def test_file_values(self):
        diff = volumes.difference(self.old, self.new)
        diff[3, 3] = np.nan
        out = volumes.for_file(diff)
        self.assertEqual(out[9, 9], 0.0)
        self.assertEqual(out[3, 3], volumes.NODATA)
        self.assertEqual(out[0, 0], -15.0)


if __name__ == "__main__":
    unittest.main()
