# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Линейка: окружность и единицы."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import measure as ms  # noqa: E402
from ellipsoid import A  # noqa: E402


class TestDestination(unittest.TestCase):

    def test_north_degree(self):
        lat, lon = ms.destination(58.0, 56.0, 0.0, math.radians(1.0) * A)
        self.assertAlmostEqual(lat, 59.0, 9)
        self.assertAlmostEqual(lon, 56.0, 9)

    def test_east_on_equator(self):
        lat, lon = ms.destination(0.0, 179.5, 90.0, math.radians(1.0) * A)
        self.assertAlmostEqual(lat, 0.0, 9)
        self.assertAlmostEqual(lon, -179.5, 9)


class TestUnits(unittest.TestCase):

    def test_convert(self):
        self.assertEqual(ms.convert(2500.0, "km", ms.LENGTH_UNITS), 2.5)
        self.assertEqual(ms.convert(3.0e4, "ha", ms.AREA_UNITS), 3.0)

    def test_number(self):
        self.assertEqual(ms.number(12.345), "12.35")
        self.assertEqual(ms.number(12345.67), "12 345.7")
        self.assertEqual(ms.number(0.01234), "0.0123")


if __name__ == "__main__":
    unittest.main()
