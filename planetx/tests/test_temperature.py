# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Температура: адреса слоёв, прозрачность, шкалы."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import temperature as tm  # noqa: E402


class TestAddress(unittest.TestCase):

    def test_latest_date_and_fields(self):
        url = tm.url_template(tm.SEA)
        self.assertIn("/" + tm.SEA + "/default/default/", url)
        self.assertTrue(url.endswith("Level7/{z}/{y}/{x}.png"))


class TestOverlay(unittest.TestCase):

    def test_no_data_is_clear(self):
        rgba = np.array([[[64, 64, 64, 0], [255, 0, 0, 255]]],
                        dtype=np.uint8)
        out = tm.overlay_rgba(rgba)
        self.assertEqual(out[0, 0, 3], 0)
        self.assertEqual(out[0, 1, 3], round(255 * tm.OPACITY))
        self.assertEqual(out[0, 1, 0], round(255 * tm.OPACITY))


class TestScale(unittest.TestCase):

    def test_land_scale_in_celsius(self):
        # 200.3 K и 349.7 K у GIBS.
        self.assertAlmostEqual(tm.LAND_STOPS[0][0], -72.85, delta=0.06)
        self.assertAlmostEqual(tm.LAND_STOPS[-1][0], 76.55, delta=0.06)
        for stops in (tm.LAND_STOPS, tm.SEA_STOPS):
            values = [v for v, _ in stops]
            self.assertEqual(values, sorted(values))

    def test_ticks_inside_scales(self):
        for stops, ticks in ((tm.LAND_STOPS, tm.LAND_TICKS),
                             (tm.SEA_STOPS, tm.SEA_TICKS)):
            for tick in ticks:
                self.assertTrue(0.0 <= tm.share(stops, tick) <= 1.0)

    def test_color_between_stops(self):
        self.assertEqual(tm.color_at(tm.SEA_STOPS, 0.1), (45, 0, 28))
        warm = tm.color_at(tm.LAND_STOPS, 40.0)
        self.assertGreater(warm[0], warm[2])


if __name__ == "__main__":
    unittest.main()
