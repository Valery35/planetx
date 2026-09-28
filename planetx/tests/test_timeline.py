# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Шкала времени записи: кадры, позы, время данных."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import timeline as tl  # noqa: E402
import tour as tr  # noqa: E402

STOPS = [tr.Stop("A", 58.0, 56.2, 5000.0, 30.0, 45.0),
         tr.Stop("B", 58.1, 56.4, 8000.0)]


class TestTimeline(unittest.TestCase):

    def test_frame_count_and_repeat(self):
        a = tl.Timeline(STOPS, 1.0)
        b = tl.Timeline(STOPS, 1.0)
        self.assertEqual(a.count, int(a.tour.duration * 25) + 1)
        self.assertEqual(a.count, b.count)
        for n in (0, a.count // 2, a.count - 1):
            pa, pb = a.frame(n).pose, b.frame(n).pose
            self.assertEqual((pa.lat, pa.lon, pa.distance, pa.heading,
                              pa.tilt),
                             (pb.lat, pb.lon, pb.distance, pb.heading,
                              pb.tilt))

    def test_starts_at_first_stop(self):
        first = tl.Timeline(STOPS, 1.0).frame(0).pose
        self.assertAlmostEqual(first.lat, 58.0)
        self.assertAlmostEqual(first.heading, 30.0)

    def test_data_time_spans_tour(self):
        line = tl.Timeline(STOPS, 1.0, data=(1000.0, 2000.0))
        self.assertEqual(line.frame(0).moment, 1000.0)
        self.assertAlmostEqual(line.frame(line.count - 1).moment, 2000.0,
                               delta=1000.0 / line.count + 1e-6)
        self.assertIsNone(tl.Timeline(STOPS, 1.0).frame(3).moment)

    def test_needs_stops(self):
        with self.assertRaises(ValueError):
            tl.Timeline([], 1.0)


if __name__ == "__main__":
    unittest.main()
