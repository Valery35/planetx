# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Режим полёта: ход самолёта по клавишам."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import flightsim  # noqa: E402
import trains  # noqa: E402


def plane():
    return flightsim.Plane(60.0, 25.0, 1000.0, 90.0)


class TestFlight(unittest.TestCase):

    def test_level_flight_keeps_height_course_and_speed(self):
        p = plane()
        flightsim.step(p, 10.0)
        self.assertAlmostEqual(p.alt, 1000.0, delta=1e-6)
        self.assertAlmostEqual(p.heading, 90.0, delta=1e-9)
        self.assertAlmostEqual(p.speed, flightsim.START_SPEED, delta=1e-6)
        run = trains._metres(60.0, 25.0, p.lat, p.lon)
        self.assertAlmostEqual(run, 10.0 * flightsim.START_SPEED, delta=1.0)
        self.assertGreater(p.lon, 25.0)

    def test_right_bank_turns_right_and_levels_back(self):
        p = plane()
        flightsim.step(p, 1.0, roll_in=1)
        self.assertAlmostEqual(p.roll, flightsim.ROLL_RATE)
        flightsim.step(p, 3.0)
        self.assertGreater(p.heading, 90.5)
        self.assertEqual(p.roll, 0.0)
        p = plane()
        flightsim.step(p, 1.0, roll_in=-1)
        flightsim.step(p, 1.0)
        self.assertLess(p.heading, 89.5)

    def test_nose_up_climbs_and_slows(self):
        p = plane()
        flightsim.step(p, 1.0, pitch_in=1)
        self.assertAlmostEqual(p.pitch, flightsim.PITCH_RATE)
        flightsim.step(p, 5.0)
        self.assertGreater(p.alt, 1050.0)
        self.assertGreater(p.climb, 0.0)
        self.assertLess(p.speed, flightsim.START_SPEED)
        flightsim.step(p, 10.0, pitch_in=1)
        self.assertEqual(p.pitch, flightsim.PITCH_MAX)

    def test_throttle_accelerates_to_top_speed(self):
        p = plane()
        flightsim.step(p, 3.0, throttle_in=1)
        self.assertEqual(p.throttle, 1.0)
        flightsim.step(p, 300.0)
        self.assertAlmostEqual(p.speed, flightsim.MAX_SPEED, delta=0.5)

    def test_stall_drops_nose(self):
        p = plane()
        p.speed = flightsim.STALL - 5.0
        p.throttle = 0.0
        flightsim.step(p, 1.0)
        self.assertLess(p.pitch, 0.0)

    def test_touching_ground_ends_flight(self):
        p = plane()
        flightsim.step(p, 2.0, pitch_in=-1)
        flightsim.step(p, 60.0, ground=900.0)
        self.assertTrue(p.crashed)
        self.assertEqual(p.alt, 900.0)
        lat = p.lat
        flightsim.step(p, 5.0)
        self.assertEqual(p.lat, lat)

    def test_readout(self):
        p = plane()
        out = flightsim.readout(p, 200.0)
        self.assertAlmostEqual(out["speed"], 500.0)
        self.assertEqual(out["height"], 800.0)
        self.assertAlmostEqual(out["throttle"], 100.0 * p.throttle)


class TestHud(unittest.TestCase):

    def test_tape_marks_around_value(self):
        marks = flightsim.tape(1013.0, 100.0, 500.0)
        self.assertEqual([m for m, _ in marks],
                         [600.0, 700.0, 800.0, 900.0, 1000.0, 1100.0,
                          1200.0, 1300.0, 1400.0, 1500.0])
        self.assertAlmostEqual(dict(marks)[1000.0], -13.0)

    def test_heading_tape_wraps_over_north(self):
        marks = flightsim.heading_tape(355.0, 10.0, 20.0)
        self.assertEqual([m for m, _ in marks], [340.0, 350.0, 0.0, 10.0])
        self.assertAlmostEqual(marks[2][1], 5.0)

    def test_ladder_follows_pitch(self):
        steps = flightsim.ladder(12.0, 5.0, 10.0)
        self.assertEqual([m for m, _ in steps], [5.0, 10.0, 15.0, 20.0])
        self.assertAlmostEqual(dict(steps)[10.0], -2.0)
        self.assertEqual(flightsim.ladder(85.0, 5.0, 10.0)[-1][0], 90.0)

    def test_horizon_offset_matches_projection(self):
        # Горизонт при тангаже 10° вверх стоит ниже середины кадра на
        # focal · tg 10°.
        focal = 500.0
        offset = flightsim.ladder_offset(0.0 - 10.0, focal)
        self.assertAlmostEqual(offset, -focal * math.tan(math.radians(10)))


class TestKinds(unittest.TestCase):

    def test_fighter_and_light_top_speeds(self):
        tops = {}
        for kind in (flightsim.FIGHTER, flightsim.LIGHT):
            p = flightsim.Plane(60.0, 25.0, 9000.0, 90.0, kind=kind)
            self.assertEqual(p.speed, p.spec.start)
            p.throttle = 1.0
            flightsim.step(p, 600.0, throttle_in=1)
            tops[kind] = p.speed * 3.6
        self.assertAlmostEqual(tops[flightsim.FIGHTER], 1998.0, delta=5.0)
        self.assertAlmostEqual(tops[flightsim.LIGHT], 342.0, delta=3.0)

    def test_fighter_banks_faster(self):
        rolls = []
        for kind in (flightsim.FIGHTER, flightsim.LIGHT):
            p = flightsim.Plane(60.0, 25.0, 1000.0, 90.0, kind=kind)
            flightsim.step(p, 0.5, roll_in=1)
            rolls.append(p.roll)
        self.assertGreater(rolls[0], rolls[1])


if __name__ == "__main__":
    unittest.main()
