# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимок вида: размеры, масштаб надписей, место на странице."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import snapshot as sn  # noqa: E402


class TestSizes(unittest.TestCase):

    def test_a4_width_at_300_dpi(self):
        # 190 мм при 300 dpi - 2244 пикселя.
        self.assertEqual(sn.layout_pixels(190.0, 95.0, 300.0), (2244, 1122))

    def test_clamp_keeps_aspect(self):
        w, h = sn.clamp_size(20000, 10000)
        self.assertEqual((w, h), (sn.MAX_SIDE, sn.MAX_SIDE // 2))
        self.assertEqual(sn.clamp_size(0, 0), (sn.MIN_SIDE, sn.MIN_SIDE))

    def test_ratios(self):
        self.assertAlmostEqual(sn.layout_ratio(96.0), 1.0)
        self.assertAlmostEqual(sn.layout_ratio(300.0), 3.125)
        # Окно 1600 логических пикселей на экране 200 %, снимок вдвое шире
        # кадра окна: надписи вдвое крупнее, чем в окне.
        self.assertAlmostEqual(sn.file_ratio(2.0, 3200, 6400), 4.0)


class TestPage(unittest.TestCase):

    def test_landscape_a4_wide_view(self):
        w, h = sn.fit_on_page(297.0, 210.0, 16.0 / 9.0)
        self.assertAlmostEqual(w, 277.0)
        self.assertAlmostEqual(h, 277.0 * 9.0 / 16.0)

    def test_tall_view_limited_by_height(self):
        w, h = sn.fit_on_page(297.0, 210.0, 1.0)
        self.assertAlmostEqual((w, h), (190.0, 190.0))

    def test_letterbox_centered(self):
        self.assertEqual(sn.letterbox(4000, 1000, 800, 600),
                         (0, 200, 800, 400))
        self.assertEqual(sn.letterbox(1000, 1000, 800, 600),
                         (100, 0, 700, 600))


if __name__ == "__main__":
    unittest.main()
