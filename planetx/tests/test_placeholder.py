# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Заглушки вместо снимка и окно тайла в картинке предка."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import placeholder as ph  # noqa: E402


def tile(color):
    out = np.zeros((256, 256, 4), dtype=np.uint8)
    out[..., :3] = color
    out[..., 3] = 255
    return out


class TestPlaceholder(unittest.TestCase):

    def test_esri_gray_with_text(self):
        # Как у Esri: 204 серого, по середине белая надпись, 94 %.
        rgba = tile((204, 204, 204))
        rgba[110:145, 60:196, :3] = 255
        self.assertTrue(ph.is_placeholder(rgba))

    def test_imagery_is_not(self):
        rng = np.random.default_rng(1)
        rgba = tile((0, 0, 0))
        rgba[..., :3] = rng.integers(60, 120, (256, 256, 3))
        self.assertFalse(ph.is_placeholder(rgba))

    def test_flat_water_is_not(self):
        # Ровная вода не серая: каналы различаются.
        self.assertFalse(ph.is_placeholder(tile((20, 60, 110))))

    def test_noisy_snow_is_not(self):
        # Снег в JPEG с шумом: серый, но не одного точного цвета.
        rng = np.random.default_rng(2)
        rgba = tile((0, 0, 0))
        v = rng.integers(240, 256, (256, 256))
        rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = v
        self.assertFalse(ph.is_placeholder(rgba))

    def test_empty(self):
        self.assertFalse(ph.is_placeholder(None))


class TestWindow(unittest.TestCase):

    def test_ancestor(self):
        self.assertEqual(ph.ancestor((19, 345884, 152543), 2),
                         (17, 86471, 38135))

    def test_quarter_of_parent(self):
        self.assertEqual(ph.crop_window((5, 0, 0), 1), (0, 0, 128))
        self.assertEqual(ph.crop_window((5, 1, 0), 1), (128, 0, 128))
        self.assertEqual(ph.crop_window((5, 0, 1), 1), (0, 128, 128))

    def test_deep_window(self):
        # Три уровня вверх: кусок 32 пикселя, место по младшим битам.
        self.assertEqual(ph.crop_window((10, 13, 6), 3), (5 * 32, 6 * 32,
                                                          32))


if __name__ == "__main__":
    unittest.main()
