# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Магнитные аномалии EMAG2v3: запись значений, раскраска, пиксель."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import emag  # noqa: E402


class TestValues(unittest.TestCase):
    def test_round_trip_and_empty(self):
        values = np.array([[-250.4, 0.0], [312.6, np.nan]])
        rgb = emag.encode(values)
        back = emag.decode(rgb)
        self.assertEqual(back[0, 0], -250.0)
        self.assertEqual(back[1, 0], 313.0)
        self.assertTrue(math.isnan(back[1, 1]))
        self.assertEqual(rgb[1, 1].tolist(), [0, 0, 0])
        # Ноль нТл - не «нет данных».
        self.assertEqual(back[0, 1], 0.0)

    def test_colors_sides_and_transparency(self):
        out = emag.colors(np.array([-300.0, 0.0, 300.0, np.nan]))
        self.assertGreater(out[0, 2], out[0, 0])  # слабее - синее
        self.assertGreater(out[2, 0], out[2, 2])  # сильнее - краснее
        self.assertEqual(out[3].tolist(), [0, 0, 0, 0])
        self.assertEqual(out[1, 3], round(255 * emag.OPACITY))
        # Альфа премножена: цвет не ярче альфы.
        self.assertTrue(np.all(out[:3, :3] <= out[:3, 3:4]))

    def test_pixel_of_point(self):
        (x, y), (column, row) = emag.pixel_of(0.0, 0.0, 1)
        self.assertEqual((x, y, column, row), (1, 1, 0, 0))
        (x, y), _ = emag.pixel_of(58.0, 56.25, emag.MAX_LEVEL)
        self.assertEqual((x, y), (21, 9))

    def test_value_at(self):
        rgb = emag.encode(np.array([[np.nan, -42.0]]))
        self.assertIsNone(emag.value_at(rgb, 0, 0))
        self.assertEqual(emag.value_at(rgb, 1, 0), -42.0)


if __name__ == "__main__":
    unittest.main()
