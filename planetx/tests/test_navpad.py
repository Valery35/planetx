# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Экранные органы навигации: кольцо, джойстики, ползунок."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import navpad as np_  # noqa: E402


class TestRing(unittest.TestCase):

    def test_angles_clockwise_from_top(self):
        self.assertAlmostEqual(np_.ring_angle(0.0, -1.0), 0.0)
        self.assertAlmostEqual(np_.ring_angle(1.0, 0.0), 90.0)
        self.assertAlmostEqual(np_.ring_angle(0.0, 1.0), 180.0)
        self.assertAlmostEqual(np_.ring_angle(-1.0, 0.0), 270.0)

    def test_delta_is_shortest(self):
        self.assertAlmostEqual(np_.angle_delta(350.0, 10.0), 20.0)
        self.assertAlmostEqual(np_.angle_delta(10.0, 350.0), -20.0)

    def test_north_follows_ring(self):
        # Кольцо тянут по часовой на 30° - буква N уходит туда же.
        heading = 40.0
        turned = heading + np_.ring_turn(0.0, 30.0)
        self.assertAlmostEqual(
            np_.angle_delta(np_.north_angle(heading),
                            np_.north_angle(turned)), 30.0)


class TestSticks(unittest.TestCase):

    def test_stick_is_clamped(self):
        sx, sy = np_.stick(30.0, 40.0, 10.0)
        self.assertAlmostEqual(math.hypot(sx, sy), 1.0)
        self.assertEqual(np_.stick(5.0, 0.0, 10.0), (0.5, 0.0))

    def test_look_up_raises_tilt(self):
        dh, dt = np_.look_step(0.0, -1.0, 1.0)
        self.assertEqual(dh, 0.0)
        self.assertAlmostEqual(dt, np_.LOOK_RATE)

    def test_move_up_goes_forward(self):
        forward, right = np_.move_step(0.0, -1.0, 2.0, 1000.0)
        self.assertAlmostEqual(forward, 2.0 * np_.MOVE_RATE * 1000.0)
        self.assertEqual(right, 0.0)


class TestZoom(unittest.TestCase):

    def test_plus_halves_in_a_second(self):
        self.assertAlmostEqual(np_.zoom_factor(1, 1.0), 0.5)
        self.assertAlmostEqual(np_.zoom_factor(-1, 1.0), 2.0)

    def test_slider_round_trip_and_ends(self):
        for d in (150.0, 3000.0, 1.0e6):
            self.assertAlmostEqual(
                np_.slider_distance(np_.slider_share(d)) / d, 1.0)
        self.assertEqual(np_.slider_share(1.0), 0.0)
        self.assertEqual(np_.slider_share(1.0e9), 1.0)


if __name__ == "__main__":
    unittest.main()
