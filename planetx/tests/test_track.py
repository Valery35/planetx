# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Растущие треки: путь к моменту, положение, азимут."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import track as tk  # noqa: E402

# Машина идёт на север 100 с, потом на восток. Лось стартует позже.
ITEMS = [("car", 0.0, 58.00, 56.00), ("car", 100.0, 58.10, 56.00),
         ("car", 200.0, 58.10, 56.20), ("car", 100.0, 58.10, 56.00),
         ("elk", 150.0, 57.00, 55.00), ("elk", 250.0, 57.00, 55.10)]


class TestTrack(unittest.TestCase):

    def setUp(self):
        self.track = tk.Track(ITEMS)

    def by_key(self, t):
        return {p.key: p for p in self.track.at(t)}

    def test_range_and_duplicates(self):
        self.assertEqual((self.track.start, self.track.end), (0.0, 250.0))
        self.assertEqual(len(self.track.objects["car"][0]), 3)

    def test_growing_path_and_interpolation(self):
        car = self.by_key(50.0)["car"]
        self.assertAlmostEqual(car.lat, 58.05)
        self.assertEqual(len(car.path), 2)
        self.assertEqual(car.path[-1], (car.lat, car.lon))
        later = self.by_key(150.0)["car"]
        self.assertEqual(len(later.path), 3)
        self.assertAlmostEqual(later.lon, 56.10)

    def test_heading_follows_motion(self):
        self.assertLess(abs(self.by_key(50.0)["car"].heading) % 360.0, 0.5)
        self.assertAlmostEqual(self.by_key(180.0)["car"].heading, 90.0,
                               delta=1.0)

    def test_not_started_and_finished(self):
        self.assertNotIn("elk", self.by_key(100.0))
        end = self.by_key(1000.0)["car"]
        self.assertEqual((end.lat, end.lon), (58.10, 56.20))
        whole = {p.key: p for p in self.track.at(None)}
        self.assertEqual(len(whole["car"].path), 3)
        self.assertEqual(len(whole["elk"].path), 2)

    def test_standing_object_has_no_heading(self):
        one = tk.Track([("x", 0.0, 1.0, 2.0)]).at(10.0)[0]
        self.assertTrue(math.isnan(one.heading))
        self.assertEqual(tk.Track([]).start, None)


if __name__ == "__main__":
    unittest.main()
