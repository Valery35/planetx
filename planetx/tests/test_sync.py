# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Синхронизация с картой: полоса на местности и сравнение видов."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import sync as sy  # noqa: E402


class TestGround(unittest.TestCase):

    def test_round_trip(self):
        for distance in (500.0, 2.0e4, 3.0e6):
            for aspect in (0.7, 1.0, 1.8):
                w, h = sy.ground_size(distance, 45.0, aspect)
                self.assertAlmostEqual(
                    sy.distance_for(w, h, 45.0, aspect) / distance, 1.0)

    def test_wide_map_fits_by_width(self):
        # Карта шире кадра глобуса: расстояние берётся по ширине.
        d = sy.distance_for(1000.0, 100.0, 45.0, 1.5)
        w, h = sy.ground_size(d, 45.0, 1.5)
        self.assertAlmostEqual(w, 1000.0)
        self.assertGreater(h, 100.0)

    def test_ground_is_capped(self):
        w, h = sy.ground_size(1.0e9, 45.0, 2.0)
        self.assertEqual((w, h), (sy.MAX_GROUND, sy.MAX_GROUND))


class TestArc(unittest.TestCase):

    def test_degree_of_meridian(self):
        self.assertAlmostEqual(sy.arc(0, 0, 1, 0) / 111319.5, 1.0, 3)

    def test_across_antimeridian(self):
        self.assertAlmostEqual(sy.arc(0, 179.5, 0, -179.5),
                               sy.arc(0, 0, 0, 1.0), 3)

    def test_over_the_pole(self):
        # Через полюс: два градуса дуги, а не половина параллели.
        self.assertAlmostEqual(sy.arc(89, 0, 89, 180),
                               2 * math.radians(1) * sy.A, 0)


class TestSameView(unittest.TestCase):

    def test_echo_is_same(self):
        a = (58.0, 56.0, 10000.0)
        self.assertTrue(sy.same_view(a, (58.0001, 56.0001, 10050.0)))

    def test_shift_and_zoom_differ(self):
        a = (58.0, 56.0, 10000.0)
        self.assertFalse(sy.same_view(a, (58.01, 56.0, 10000.0)))
        self.assertFalse(sy.same_view(a, (58.0, 56.0, 11000.0)))
        self.assertFalse(sy.same_view(a, None))


if __name__ == "__main__":
    unittest.main()
