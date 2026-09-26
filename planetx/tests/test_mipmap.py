# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Уровни мипмапов на NumPy."""
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

from mipmap import mip_chain  # noqa: E402


class TestMipChain(unittest.TestCase):

    def test_sizes_down_to_one(self):
        rgba = np.zeros((256, 256, 4), dtype=np.uint8)
        levels = mip_chain(rgba)
        self.assertEqual([lv.shape[0] for lv in levels],
                         [256, 128, 64, 32, 16, 8, 4, 2, 1])
        self.assertTrue(all(lv.dtype == np.uint8 for lv in levels))
        self.assertTrue(all(lv.flags["C_CONTIGUOUS"] for lv in levels))

    def test_average_of_blocks(self):
        rgba = np.array([[[0, 10, 255, 255], [4, 10, 255, 255]],
                         [[8, 11, 0, 255], [12, 11, 0, 255]]],
                        dtype=np.uint8)
        top = mip_chain(rgba)[1]
        self.assertEqual(top.shape, (1, 1, 4))
        # Средние 6, 10.5, 127.5 и 255, округление к чётному.
        self.assertEqual(tuple(top[0, 0]), (6, 10, 128, 255))

    def test_mean_colour_kept(self):
        rng = np.random.default_rng(3)
        rgba = rng.integers(0, 256, (256, 256, 4), dtype=np.uint8)
        last = mip_chain(rgba)[-1][0, 0].astype(float)
        # Одно округление - ошибка не больше половины единицы.
        self.assertLessEqual(np.abs(last - rgba.reshape(-1, 4).mean(axis=0))
                             .max(), 0.5)

    def test_first_level_is_the_picture(self):
        rgba = np.random.default_rng(4).integers(0, 256, (8, 8, 4),
                                                 dtype=np.uint8)
        self.assertTrue(np.array_equal(mip_chain(rgba)[0], rgba))

    def test_non_square(self):
        rgba = np.zeros((4, 1, 4), dtype=np.uint8)
        self.assertEqual([lv.shape[:2] for lv in mip_chain(rgba)],
                         [(4, 1), (2, 1), (1, 1)])


if __name__ == "__main__":
    unittest.main()
