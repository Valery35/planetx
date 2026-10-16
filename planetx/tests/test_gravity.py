# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Синтез аномалии силы тяжести tools/build_gravity.py на простых полях."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "tools"))

import build_gravity as bg  # noqa: E402

GM = 3.986004415e14
A = 6378136.3


def field(terms, nmax=8, step=10.0):
    c = np.zeros((nmax + 1, nmax + 1))
    s = np.zeros((nmax + 1, nmax + 1))
    for (n, m, cnm, snm) in terms:
        c[n, m] = cnm
        s[n, m] = snm
    return bg.synthesis(GM, A, c, s, nmax, step)


class TestSynthesis(unittest.TestCase):

    def test_zonal_term(self):
        # Δg = GM / a² (n - 1) C̄20 P̄20, P̄20 = √5 (3 sin²φ - 1) / 2.
        lats, grid = field([(2, 0, 1e-6, 0.0)])
        t = np.sin(np.radians(lats))
        want = GM / A ** 2 * 1e5 * 1e-6 * math.sqrt(5) * (3 * t * t - 1) / 2
        for column in range(grid.shape[1]):
            self.assertTrue(np.allclose(grid[:, column], want, atol=1e-9))

    def test_tesseral_phase(self):
        # C̄31 cos λ + S̄31 sin λ - по долготе cos(λ - λ0), tg λ0 = S / C.
        lats, grid = field([(3, 1, 2e-7, 1e-7)], step=5.0)
        lons = -180.0 + 2.5 + np.arange(grid.shape[1]) * 5.0
        row = int(np.argmax(np.abs(grid[:, 0])))
        shape = np.cos(np.radians(lons) - math.atan2(1e-7, 2e-7))
        scale = grid[row] / shape
        good = np.abs(shape) > 0.2
        self.assertTrue(np.allclose(scale[good], scale[good][0], rtol=1e-9))
        # Величина: P̄31 = √42 / 4 · cos φ (5 sin²φ - 1), множитель n - 1 = 2.
        t = math.sin(math.radians(lats[row]))
        u = math.cos(math.radians(lats[row]))
        p31 = math.sqrt(42.0) / 4.0 * u * (5 * t * t - 1)
        amp = GM / A ** 2 * 1e5 * 2 * math.hypot(2e-7, 1e-7) * p31
        self.assertAlmostEqual(abs(scale[good][0]), abs(amp), delta=abs(amp)
                               * 1e-9)

    def test_normal_field_j2(self):
        # C̄20 нормального поля GRS80 - около -4.8417e-4.
        zonals = bg.normal_zonals(bg.GRS_GM, bg.GRS_A)
        self.assertAlmostEqual(zonals[2], -4.84166854e-4, places=10)
        self.assertAlmostEqual(zonals[4] * 1e7, 7.90304, places=3)


if __name__ == "__main__":
    unittest.main()
