# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
# Перенесено из Isoliner, grid_isolines/tests/test_topo_surface.py.
# Там - GPL-2.0-or-later, владелец тот же.
"""Тесты морфометрии: уклон, экспозиция, вершины."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import topo_surface as ts  # noqa: E402


class TestSlopeAspect(unittest.TestCase):

    def test_east_facing_plane(self):
        # высота падает на восток: экспозиция 90, уклон atan(g)
        cell = 10.0
        g = 0.2  # м на м
        nx, ny = 30, 20
        z = np.tile(1000.0 - np.arange(nx) * g * cell, (ny, 1))
        slope, aspect = ts.slope_aspect(z, cell)
        inner = (slice(1, -1), slice(1, -1))
        want = math.degrees(math.atan(g))
        self.assertTrue(np.allclose(slope[inner], want, atol=1e-6))
        self.assertTrue(np.allclose(aspect[inner], 90.0, atol=1e-6))

    def test_north_facing_plane(self):
        # высота растёт на юг (по строкам): смотрит на север, 0 градусов
        cell = 5.0
        ny, nx = 25, 15
        z = np.arange(ny, dtype=float)[:, None] * 1.0 + np.zeros((ny, nx))
        slope, aspect = ts.slope_aspect(z, cell)
        inner = (slice(1, -1), slice(1, -1))
        self.assertTrue(np.allclose(aspect[inner], 0.0, atol=1e-6))
        self.assertTrue((slope[inner] > 0).all())

    def test_flat_aspect_minus_one(self):
        z = np.full((10, 10), 500.0)
        slope, aspect = ts.slope_aspect(z, 30.0)
        self.assertTrue(np.allclose(slope, 0.0))
        self.assertTrue(np.allclose(aspect, -1.0))

    def test_nodata_hole_gives_nan(self):
        z = np.tile(np.arange(12, dtype=float), (10, 1))
        mask = np.zeros_like(z, dtype=bool)
        mask[5, 6] = True
        slope, aspect = ts.slope_aspect(z, 10.0, nodata_mask=mask)
        self.assertTrue(np.isnan(slope[5, 6]))
        self.assertTrue(np.isnan(slope[5, 5]))  # сосед дыры тоже NaN
        self.assertFalse(np.isnan(slope[5, 3]))


class TestPeaks(unittest.TestCase):

    def _two_hills(self):
        ny, nx = 60, 80
        yy, xx = np.mgrid[0:ny, 0:nx]
        z = np.zeros((ny, nx))
        z += 50.0 * np.exp(-(((xx - 20) ** 2 + (yy - 30) ** 2) / 60.0))
        z += 30.0 * np.exp(-(((xx - 60) ** 2 + (yy - 25) ** 2) / 40.0))
        z += 0.5 * np.exp(-(((xx - 40) ** 2 + (yy - 50) ** 2) / 10.0))
        return z

    def test_two_hills_found_bump_filtered(self):
        z = self._two_hills()
        peaks = ts.find_peaks(z, cell=10.0, radius_m=80.0, min_drop=5.0)
        self.assertEqual(len(peaks), 2)
        (r1, c1, z1, d1), (r2, c2, z2, d2) = peaks
        self.assertGreater(z1, z2)  # сортировка по убыванию высоты
        self.assertAlmostEqual(r1, 30, delta=1)
        self.assertAlmostEqual(c1, 20, delta=1)
        self.assertAlmostEqual(r2, 25, delta=1)
        self.assertAlmostEqual(c2, 60, delta=1)
        self.assertGreater(d1, 5.0)

    def test_min_drop_zero_keeps_bump(self):
        z = self._two_hills()
        peaks = ts.find_peaks(z, cell=10.0, radius_m=80.0, min_drop=0.1)
        self.assertEqual(len(peaks), 3)

    def test_plateau_gives_single_peak(self):
        z = np.zeros((30, 30))
        z[10:13, 10:13] = 7.0  # плоская макушка 3x3
        peaks = ts.find_peaks(z, cell=10.0, radius_m=50.0, min_drop=1.0)
        self.assertEqual(len(peaks), 1)

    def test_radius_separates(self):
        z = np.zeros((20, 60))
        z[10, 10] = 5.0
        z[10, 40] = 6.0
        near = ts.find_peaks(z, cell=10.0, radius_m=100.0, min_drop=0.5)
        far = ts.find_peaks(z, cell=10.0, radius_m=400.0, min_drop=0.5)
        self.assertEqual(len(near), 2)
        self.assertEqual(len(far), 1)


class TestExtremes(unittest.TestCase):
    """Вершины и ямы разом: обёртка find_extremes.

    Пришло из чата сообщества: поверхность в АвтоКАДе по одним
    горизонталям кладёт плоскую шапку на каждую замкнутую горизонталь,
    и пикеты нужны сразу на ямы и вершины.
    """

    def _hill_and_pit(self):
        ny, nx = 60, 80
        yy, xx = np.mgrid[0:ny, 0:nx]
        z = np.full((ny, nx), 100.0)
        z += 50.0 * np.exp(-(((xx - 20) ** 2 + (yy - 30) ** 2) / 60.0))
        z -= 40.0 * np.exp(-(((xx - 60) ** 2 + (yy - 30) ** 2) / 40.0))
        return z

    def test_both_kinds_found(self):
        got = ts.find_extremes(self._hill_and_pit(), cell=10.0,
                               radius_m=150.0, min_drop=5.0)
        kinds = sorted(t[4] for t in got)
        self.assertEqual(kinds, ["peak", "pit"])

    def test_pit_keeps_true_elevation_and_positive_depth(self):
        """У ямы z это её настоящая отметка, а drop положительная глубина.

        Обращение рельефа - деталь реализации, наружу знаки выходят
        исходные: точка ямы обязана лечь на поверхность в АвтоКАДе, а
        не отразиться от неё.
        """
        z = self._hill_and_pit()
        got = ts.find_extremes(z, cell=10.0, radius_m=150.0, min_drop=5.0)
        pit = [t for t in got if t[4] == "pit"][0]
        r, c, zv, dv, _k = pit
        self.assertAlmostEqual(zv, float(z[r, c]), places=9)
        self.assertLess(zv, 100.0)      # яма ниже равнины
        self.assertGreater(dv, 5.0)     # глубина положительная

    def test_peak_half_matches_find_peaks(self):
        """Вершинная половина в точности совпадает с прежним find_peaks.

        Старые прогоны по вершинам воспроизводятся, добавились только
        ямы.
        """
        z = self._hill_and_pit()
        old = ts.find_peaks(z, cell=10.0, radius_m=150.0, min_drop=5.0)
        new = [t[:4] for t in ts.find_extremes(z, cell=10.0, radius_m=150.0,
                                               min_drop=5.0)
               if t[4] == "peak"]
        self.assertEqual(sorted(old), sorted(new))

    def test_flat_field_gives_nothing(self):
        z = np.full((40, 40), 7.0)
        self.assertEqual(ts.find_extremes(z, cell=10.0, radius_m=100.0,
                                          min_drop=1.0), [])

    def test_nodata_respected(self):
        z = self._hill_and_pit()
        mask = np.zeros(z.shape, dtype=bool)
        mask[20:40, 50:70] = True     # яма вырезана из данных
        got = ts.find_extremes(z, cell=10.0, radius_m=150.0, min_drop=5.0,
                               nodata_mask=mask)
        self.assertEqual([t[4] for t in got], ["peak"])


if __name__ == "__main__":
    unittest.main()
