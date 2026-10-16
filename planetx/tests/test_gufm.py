# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Модель gufm1: B-сплайны, сшивка с IGRF, склонение в Лондоне.

Файл модели в модуль не входит. Проверка на настоящем файле идёт, если
переменная PLANETX_GUFM1 указывает на gufm1.txt."""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))

import geomag  # noqa: E402
from test_geomag import load  # noqa: E402


class TestSpline(unittest.TestCase):

    def test_partition_of_unity(self):
        knots = np.arange(1582.5, 1600.1, 2.5)
        for t in (1590.0, 1591.3, 1592.5):
            b = geomag.bspline(t, knots)
            self.assertAlmostEqual(float(b.sum()), 1.0, places=12)
            self.assertTrue(np.all(b >= 0.0))

    def test_synthetic_file(self):
        # Два сплайна степени 1 - коэффициенты постоянны по времени.
        nmax, nspl = 1, 4
        knots = [1580.0 + 2.5 * k for k in range(nspl + 4)]
        rows = [[-30000.0, -2000.0, 5000.0]] * nspl
        text = "header\n{} {}\n{}\n{}\n".format(
            nmax, nspl, " ".join(str(k) for k in knots),
            " ".join(str(v) for row in rows for v in row))
        model = geomag.parse_gufm(text)
        coeffs = model.at(1590.0)
        self.assertTrue(np.allclose(coeffs, [-30000.0, -2000.0, 5000.0]))
        self.assertIsNone(model.at(1500.0))
        with self.assertRaises(ValueError):
            geomag.parse_gufm("header\n1 2 3")


@unittest.skipUnless(os.environ.get("PLANETX_GUFM1"),
                     "нет PLANETX_GUFM1 - файла gufm1.txt")
class TestRealGufm(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(os.environ["PLANETX_GUFM1"], encoding="ascii") as fh:
            cls.gufm = geomag.parse_gufm(fh.read())
        cls.igrf, _ = load()

    def test_meets_igrf_in_1900(self):
        g = self.gufm.at(1900.0)
        i = self.igrf.at(1900.0)
        for k in range(3):
            self.assertLess(abs(g[k] - i[k]), 60.0, k)

    def test_london_declination(self):
        model = geomag.Combined(self.igrf, self.gufm)

        def decl(year):
            return geomag.field(model, 51.5, -0.12, year)["declination"]
        # Геллибранд, 1634, Дептфорд - 4.1° в. д.
        self.assertLess(abs(decl(1634.0) - 4.1), 1.5)
        # Знак меняется около 1660 года, наибольшее западное - около
        # 1820 года, 24°.
        self.assertGreater(decl(1650.0), 0.0)
        self.assertLess(decl(1670.0), 0.0)
        self.assertLess(abs(decl(1820.0) + 24.0), 1.0)
        # После 1900 года - IGRF.
        self.assertEqual(model.part(1950.0), self.igrf)
        self.assertEqual(model.part(1700.0), self.gufm)
        self.assertIsNone(model.part(1500.0))


if __name__ == "__main__":
    unittest.main()
