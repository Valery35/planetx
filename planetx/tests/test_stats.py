# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты сводки значений участка."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import stats  # noqa: E402


class TestDescribe(unittest.TestCase):

    def test_values_of_known_row(self):
        rep = stats.describe(np.arange(1.0, 102.0))
        self.assertEqual(rep.count, 101)
        self.assertAlmostEqual(rep.mean, 51.0)
        self.assertAlmostEqual(rep.std, np.sqrt(850.0))
        self.assertEqual((rep.low, rep.high), (1.0, 101.0))
        self.assertEqual((rep.p10, rep.q1, rep.median, rep.q3, rep.p90),
                         (11.0, 26.0, 51.0, 76.0, 91.0))

    def test_empty_cells_stay_outside(self):
        rep = stats.describe([[1.0, np.nan], [np.inf, 3.0]])
        self.assertEqual(rep.count, 2)
        self.assertEqual(rep.mean, 2.0)

    def test_nothing_to_describe(self):
        self.assertIsNone(stats.describe([np.nan, -np.inf]))
        self.assertIsNone(stats.describe([]))


class TestRounded(unittest.TestCase):

    def test_three_digits(self):
        self.assertEqual(stats.rounded(0.0284), "0.03")
        self.assertEqual(stats.rounded(28.74), "28.7")
        self.assertEqual(stats.rounded(-1234.5), "-1234")


if __name__ == "__main__":
    unittest.main()
