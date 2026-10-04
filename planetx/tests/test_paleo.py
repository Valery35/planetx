# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Палеогеография: возрасты, периоды, раскраска и отмывка карт."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import paleo  # noqa: E402


class TestPaleo(unittest.TestCase):

    def test_ages(self):
        self.assertEqual(len(paleo.AGES), 109)
        self.assertEqual((paleo.AGES[0], paleo.AGES[-1]), (0, 540))

    def test_nearest(self):
        self.assertEqual(paleo.nearest(252), 250)
        self.assertEqual(paleo.nearest(1000), 540)
        self.assertEqual(paleo.nearest(-3), 0)

    def test_tile_url_has_age_and_tile(self):
        url = paleo.TILE_URL.format(age=250, z=2, x=1, y=3)
        self.assertTrue(url.endswith("/paleomap/250/2/1/3.jpg"))

    def test_period(self):
        self.assertEqual(paleo.period(0), "quaternary")
        self.assertEqual(paleo.period(100), "cretaceous")
        self.assertEqual(paleo.period(280), "permian")
        self.assertEqual(paleo.period(600), "precambrian")

    def test_sea_is_blue_and_land_is_not(self):
        sea, land = paleo.colors([-3000.0, 500.0])
        self.assertGreater(sea[2], sea[0])
        self.assertGreater(land[1], land[2])

    def test_flat_ground_is_not_shaded(self):
        shade = paleo.hillshade(np.full((20, 40), 100.0), 0.1)
        self.assertTrue(np.allclose(shade, 1.0))

    def test_slope_to_sun_is_lighter(self):
        # Высота растёт к юго-востоку: склон смотрит на северо-запад,
        # к солнцу, и светлее равнины. Обратный склон темнее.
        rows, cols = np.mgrid[0:20, 0:40]
        towards = paleo.hillshade((rows + cols) * 50.0, 0.1)
        away = paleo.hillshade(-(rows + cols) * 50.0, 0.1)
        self.assertGreater(towards[10, 20], 1.0)
        self.assertLess(away[10, 20], 1.0)

    def test_picture_shape(self):
        image = paleo.picture(np.zeros((10, 20)), 0.1)
        self.assertEqual((image.shape, image.dtype), ((10, 20, 3), np.uint8))


if __name__ == "__main__":
    unittest.main()
