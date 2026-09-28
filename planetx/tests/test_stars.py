# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Звёзды: звёздное время, поворот неба, вид точки, файл каталога."""
import math
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "core"))

import stars  # noqa: E402

DATA = os.path.join(HERE, "data", "stars.npy")


class TestTime(unittest.TestCase):

    def test_gmst_at_j2000(self):
        self.assertAlmostEqual(math.degrees(stars.gmst(stars.UNIX_J2000)),
                               280.46061837, places=6)

    def test_sidereal_day_is_shorter(self):
        # За звёздные сутки, 86164.09 с, небо делает полный оборот.
        start = 1.8e9
        turn = stars.gmst(start + 86164.0905) - stars.gmst(start)
        self.assertAlmostEqual(math.remainder(turn, 2 * math.pi), 0.0,
                               places=4)

    def test_star_at_gmst_is_over_greenwich(self):
        when = 1.8e9
        ra = stars.gmst(when)
        ecef = stars.to_ecef(stars.sky_directions([ra], [0.3]), when)[0]
        self.assertAlmostEqual(math.atan2(ecef[1], ecef[0]), 0.0, places=9)
        self.assertAlmostEqual(math.asin(ecef[2]), 0.3, places=9)


class TestLook(unittest.TestCase):

    def test_brighter_is_bigger(self):
        size = stars.sizes([-1.46, 1.0, 6.0])
        self.assertTrue(size[0] > size[1] > size[2])
        self.assertAlmostEqual(size[2], stars.SIZE_FAINT)

    def test_colors_blue_to_red(self):
        blue, red = stars.colors([-0.3, 1.6])
        self.assertGreater(blue[2], blue[0])
        self.assertGreater(red[0], red[2])
        self.assertTrue(np.all(np.isfinite(stars.colors([np.nan]))))

    def test_fade_with_altitude(self):
        self.assertEqual(stars.fade(1000.0), 0.0)
        self.assertEqual(stars.fade(stars.FADE_HIGH), 1.0)
        self.assertTrue(0.0 < stars.fade(70000.0) < 1.0)


class TestCatalogue(unittest.TestCase):

    def test_file_has_sirius(self):
        table = np.load(DATA, allow_pickle=False)
        self.assertGreater(len(table), 5000)
        self.assertLessEqual(table[:, 2].max(), stars.MAX_MAG)
        sirius = table[table[:, 2].argmin()]
        self.assertAlmostEqual(math.degrees(sirius[0]), 101.287, places=2)
        self.assertAlmostEqual(math.degrees(sirius[1]), -16.716, places=2)


if __name__ == "__main__":
    unittest.main()
