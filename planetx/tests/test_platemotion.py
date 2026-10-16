# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Скорости плит NNR-MORVEL56: плита в точке, скорость, стрелки."""
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))

import platemotion as pm  # noqa: E402

DATA = os.path.join(os.path.dirname(HERE), "data", "plate_motion.json")


def load():
    with open(DATA, encoding="utf-8") as fh:
        return pm.read(fh.read())


class TestPlates(unittest.TestCase):

    def setUp(self):
        self.motion = load()

    def test_plate_at_known_places(self):
        cases = {(0.0, -150.0): "PA", (10.0, 170.0): "PA",
                 (-85.0, 0.0): "AN", (55.75, 37.62): "EU",
                 (0.0, 20.0): "AF", (40.0, -100.0): "NA",
                 (20.0, 78.0): "IN", (-25.0, 135.0): "AU",
                 (-15.0, -60.0): "SA",
                 # Исландию режет рифт: Рейкьявик - Северная Америка,
                 # восток острова - Евразия.
                 (64.1, -21.9): "NA", (65.0, -14.5): "EU"}
        for (lat, lon), code in cases.items():
            self.assertEqual(self.motion.plate_at(lat, lon), code,
                             (lat, lon))

    def test_pacific_moves_northwest_fast(self):
        # Гавайи: Тихоокеанская плита идёт на северо-запад около 70
        # мм/год в NNR (DeMets et al. 2010, Argus et al. 2011).
        code, east, north = self.motion.velocity(19.7, -155.5)
        speed, azimuth = pm.speed_azimuth(east, north)
        self.assertEqual(code, "PA")
        self.assertTrue(60.0 < speed < 80.0, speed)
        self.assertTrue(280.0 < azimuth < 310.0, azimuth)

    def test_rotation_is_rigid(self):
        # Скорость у полюса вращения - ноль, на 90° от него - ω·R.
        pole = (30.0, 40.0, 1.0)
        east, north = pm.velocity(pole, 30.0, 40.0)
        self.assertLess(math.hypot(east, north), 1e-6)
        east, north = pm.velocity(pole, -60.0, 40.0)
        expected = math.radians(1.0) / 1e6 * pm.RADIUS
        self.assertAlmostEqual(math.hypot(east, north), expected, delta=1e-6)

    def test_arrows_cover_view(self):
        found = pm.arrows(self.motion, 40.0, -100.0, 4.0e6)
        # Около ARROWS_ACROSS поперёк вида: десятки, не сотни.
        self.assertTrue(20 < len(found) < 200, len(found))
        for lat, lon, speed, azimuth, lines in found:
            self.assertEqual(len(lines), 3)
            self.assertLessEqual(abs(lat), pm.MAX_LAT)
        whole = pm.arrows(self.motion, 0.0, 0.0, 4.0e7)
        lons = sorted({round(a[1], 3) for a in whole})
        self.assertEqual(len(lons), len(set(lons)))
        self.assertTrue(30 < len(whole) < 400, len(whole))


if __name__ == "__main__":
    unittest.main()
