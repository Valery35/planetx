# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Карта тренда: наклон Тейла-Сена и тест Манна-Кендалла по пикселям."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import trend  # noqa: E402


class TestTrend(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        self.days = np.sort(rng.uniform(0.0, 6 * 365.25, 30))
        years = self.days / 365.25
        self.stack = np.zeros((30, 2, 3))
        self.stack[:, 0, 0] = 0.3 + 0.05 * years + rng.normal(0, 0.01, 30)
        self.stack[:, 0, 1] = 0.5 - 0.02 * years + rng.normal(0, 0.01, 30)
        self.stack[:, 0, 2] = rng.normal(0.4, 0.05, 30)
        self.stack[:, 1, 0] = np.nan
        self.stack[:4, 1, 0] = [0.1, 0.2, 0.3, 0.4]
        self.stack[:, 1, 1] = 0.3 + 0.05 * years
        self.stack[::3, 1, 1] = 5.0  # выбросы - облака
        self.stack[:, 1, 2] = np.nan
        self.stack[::2, 1, 2] = 0.2 + 0.1 * years[::2]

    def test_slope_and_significance(self):
        slope, p, n = trend.trend(self.stack, self.days)
        self.assertAlmostEqual(slope[0, 0], 0.05, delta=0.005)
        self.assertAlmostEqual(slope[0, 1], -0.02, delta=0.005)
        self.assertLess(p[0, 0], 0.001)
        self.assertLess(p[0, 1], 0.001)
        self.assertGreater(p[0, 2], trend.SIGNIFICANT)
        self.assertEqual(n[1, 0], 4)
        self.assertTrue(np.isnan(slope[1, 0]) and np.isnan(p[1, 0]))
        self.assertEqual(n[1, 2], 15)
        self.assertAlmostEqual(slope[1, 2], 0.1, delta=1e-9)

    def test_outliers_do_not_move_sen_slope(self):
        slope, _, _ = trend.trend(self.stack, self.days)
        self.assertAlmostEqual(slope[1, 1], 0.05, delta=0.02)

    def test_matches_direct_pairs(self):
        values = self.stack[:, 0, 2]
        pairs = [(values[j] - values[i]) / ((self.days[j] - self.days[i])
                                            / trend.YEAR)
                 for i in range(30) for j in range(i + 1, 30)]
        slope, _, _ = trend.trend(self.stack, self.days)
        self.assertAlmostEqual(slope[0, 2], float(np.median(pairs)))

    def test_chunks_give_same_result(self):
        big = np.repeat(self.stack, 50, axis=2)
        full = trend.trend(big, self.days)[0]
        saved = trend.CHUNK
        trend.CHUNK = 7
        try:
            parts = trend.trend(big, self.days)[0]
        finally:
            trend.CHUNK = saved
        np.testing.assert_allclose(full, parts, equal_nan=True)

    def test_limits_symmetric(self):
        low, high = trend.limits(np.array([[-0.2, 0.05], [np.nan, 0.1]]))
        self.assertEqual(low, -high)
        self.assertGreater(high, 0.1)


if __name__ == "__main__":
    unittest.main()
