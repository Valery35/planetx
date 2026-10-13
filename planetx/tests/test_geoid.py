# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Геоид EGM2008: чтение сетки GeographicLib и запись Terrarium."""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))

import geoid  # noqa: E402
import terrain  # noqa: E402


def pgm(values, width, height, offset=-108.0, scale=0.003):
    head = ("P5\n# Description WGS84 EGM2008, test\n# Offset {}\n"
            "# Scale {}\n{} {}\n65535\n").format(offset, scale, width,
                                                  height)
    return head.encode("ascii") + np.asarray(values, ">u2").tobytes()


class TestGeoid(unittest.TestCase):
    def test_read_pgm(self):
        grid, step = geoid.read_pgm(pgm([[0, 36000], [65535, 1000]], 2, 2))
        self.assertEqual(step, 180.0)
        self.assertAlmostEqual(grid[0, 0], -108.0)
        self.assertAlmostEqual(grid[0, 1], 0.0)
        self.assertAlmostEqual(grid[1, 0], -108.0 + 0.003 * 65535)

    def test_not_pgm(self):
        with self.assertRaises(ValueError):
            geoid.read_pgm(b"P2\n# Offset 1\n# Scale 1\n1 1\n255\n0")

    def test_terrarium_round_trip(self):
        # Тайлы геоида читает обычный разбор высот Terrarium модуля.
        heights = np.array([[-106.9, 85.73], [0.0, -2.66]])
        rgb = geoid.encode(heights)
        rgba = np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])
        back = terrain.decode(rgba, floor=None)
        self.assertTrue(np.allclose(back, heights, atol=0.005))


if __name__ == "__main__":
    unittest.main()
