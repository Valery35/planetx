# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Синтез аномалии силы тяжести tools/build_gravity.py на простых полях
и поправка Буге tools/build_bouguer.py."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "tools"))

import build_bouguer as bb  # noqa: E402
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


class TestBouguer(unittest.TestCase):
    """Поправка Буге tools/build_bouguer.py."""

    def test_land_slab(self):
        # 1000 м породы 2670 кг/м³ - 2πGρh = 111.96 мГал.
        self.assertAlmostEqual(float(bb.correction(1000.0, 1000.0)),
                               2 * math.pi * 6.674e-11 * 2670 * 1000 * 1e5,
                               places=6)
        self.assertAlmostEqual(float(bb.correction(1000.0, 1000.0)),
                               111.96, places=1)

    def test_ocean_fills_water_with_rock(self):
        # 4000 м воды: недостаток (2670 - 1030) · 4000, поправка
        # отрицательная, аномалия Буге над океаном выше свободной.
        value = float(bb.correction(-4000.0, -4000.0))
        self.assertAlmostEqual(value, -bb.SLAB * 1640.0 * 4000.0, places=6)
        self.assertLess(value, -270.0)

    def test_ice(self):
        # Лёд 2000 м на породе 500 м - порода и лёд своей плотностью.
        self.assertAlmostEqual(float(bb.correction(500.0, 2500.0)),
                               bb.SLAB * (2670 * 500 + 917 * 2000), places=6)
        # Лёд на дне ниже уровня моря: выше нуля лёд снимается, ниже нуля
        # лёд заменяется породой, воды нет.
        self.assertAlmostEqual(
            float(bb.correction(-300.0, 1700.0)),
            bb.SLAB * (917 * 1700 - (2670 - 917) * 300), places=6)

    def test_rock_equivalent(self):
        # Океан: столб воды 4000 м - порода той же недостачи массы.
        self.assertAlmostEqual(float(bb.rock_equivalent(-4000.0, -4000.0)),
                               -4000.0 * (1 - 1030.0 / 2670.0), places=6)
        self.assertAlmostEqual(float(bb.rock_equivalent(800.0, 800.0)),
                               800.0, places=6)

    def test_terrain_correction_matches_direct_sum(self):
        # Свёртка БПФ совпадает с прямой суммой Gρ/2 Σ Δh² / r³ ΔS.
        rng = np.random.default_rng(3)
        h = rng.uniform(0.0, 2000.0, (14, 40))
        dx, dy, reach = 900.0, 1100.0, 5000.0
        tc = bb.terrain_correction(h, dx, dy, reach)
        rows, cols = h.shape
        for p, q in ((7, 3), (6, 38), (2, 20)):
            total = 0.0
            for i in range(rows):
                for j in range(cols):
                    dj = (j - q + cols // 2) % cols - cols // 2
                    r = math.hypot((i - p) * dy, dj * dx)
                    if 0.0 < r <= reach and abs(dj) <= int(reach // dx):
                        total += (h[i, j] - h[p, q]) ** 2 * dx * dy / r ** 3
            want = total * 0.5 * bb.G * bb.RHO_CRUST * bb.MGAL
            self.assertAlmostEqual(tc[p, q], want, delta=want * 1e-9 + 1e-9)

    def test_flat_terrain_has_no_correction(self):
        tc = bb.terrain_correction(np.full((10, 30), 1500.0), 1000.0,
                                   1000.0, 4000.0)
        self.assertLess(float(np.abs(tc).max()), 1e-9)

    def test_block_mean(self):
        values = np.arange(30 * 60, dtype=np.float64).reshape(30, 60)
        out = bb.block_mean(values)
        self.assertEqual(out.shape, (2, 4))
        self.assertAlmostEqual(out[0, 0], values[:15, :15].mean())
        self.assertAlmostEqual(out[1, 3], values[15:, 45:].mean())


if __name__ == "__main__":
    unittest.main()
