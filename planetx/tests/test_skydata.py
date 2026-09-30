# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Данные созвездий и светила вида неба."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import skydata  # noqa: E402

DATA = skydata.load()


class TestSkyData(unittest.TestCase):

    def test_all_constellations_named(self):
        self.assertEqual(len(DATA["names"]), 88 + 1)  # Змея из двух частей
        for entry in DATA["names"]:
            self.assertTrue(entry["ru"] and entry["en"], entry)
            self.assertTrue(0.0 <= entry["ra"] < 360.0)

    def test_segments_are_short_arcs(self):
        seg = skydata.segments(DATA)
        self.assertEqual(len(seg) % 2, 0)
        norms = np.linalg.norm(seg, axis=1)
        self.assertTrue(np.allclose(norms, 1.0, atol=1e-5))
        cos = np.sum(seg[0::2] * seg[1::2], axis=1)
        # Отрезок фигуры не длиннее 60°, иначе RA перепутано со швом 0h.
        self.assertGreater(float(cos.min()), math.cos(math.radians(60.0)))

    def test_betelgeuse_in_orion(self):
        star = next(s for s in DATA["stars"] if s["en"] == "Betelgeuse")
        self.assertAlmostEqual(star["ra"], 88.79, delta=0.05)
        self.assertAlmostEqual(star["dec"], 7.41, delta=0.05)
        self.assertEqual(star["ru"], "Бетельгейзе")

    def test_bodies(self):
        points = skydata.body_points(0.0)
        self.assertEqual(points.shape, (9, 8))


if __name__ == "__main__":
    unittest.main()
