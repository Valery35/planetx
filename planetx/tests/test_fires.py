# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Пожары: разбор сводки NASA FIRMS, цвет и размер по мощности."""
import calendar
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import fires  # noqa: E402

SAMPLE = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,\
satellite,confidence,version,bright_ti5,frp,daynight
42.93438,18.87675,367,0.37,0.58,2026-10-04,0001,N20,high,2.0NRT,286.87,7.38,N
-10.5,-55.25,330.1,0.4,0.6,2026-10-04,1742,N20,nominal,2.0NRT,290.1,152.4,D
bad,row,1,1,1,2026-10-04,0001,N20,low,2.0NRT,1,1,N
1.0,2.0,300,0.4,0.6,2026-10-04,1200,N20,low,2.0NRT,290,nan,D
"""


class TestParse(unittest.TestCase):

    def test_rows_and_fields(self):
        data = fires.parse(SAMPLE)
        self.assertEqual(len(data), 2)  # строка без чисел и NaN - мимо
        self.assertAlmostEqual(data.lat[1], -10.5)
        self.assertAlmostEqual(data.frp[1], 152.4)
        self.assertEqual(data.confidence, ["high", "nominal"])
        self.assertEqual(list(data.night), [True, False])
        self.assertEqual(data.time[1], calendar.timegm(
            (2026, 10, 4, 17, 42, 0)))
        self.assertEqual(fires.span(data), (data.time[0], data.time[1]))

    def test_empty_and_foreign_text(self):
        self.assertEqual(len(fires.parse("")), 0)
        self.assertEqual(len(fires.parse("a,b\n1,2\n")), 0)
        self.assertIsNone(fires.span(fires.parse("")))


class TestLook(unittest.TestCase):

    def test_colors_follow_stops(self):
        rgb = fires.colors([1.0, 10.0, 100.0, 1000.0, 5000.0, 0.1])
        for (frp, color), got in zip(fires.FRP_STOPS, rgb[:4]):
            self.assertEqual(tuple(int(v) for v in got), color)
        self.assertEqual(tuple(int(v) for v in rgb[4]),
                         fires.FRP_STOPS[-1][1])
        self.assertEqual(tuple(int(v) for v in rgb[5]),
                         fires.FRP_STOPS[0][1])

    def test_sizes_grow_and_clip(self):
        size = fires.sizes([0.5, 1.0, 10.0, 100.0, 1e6])
        self.assertEqual(size[0], fires.MIN_SIZE)
        self.assertTrue(np.all(np.diff(size) >= 0.0))
        self.assertEqual(size[-1], fires.MAX_SIZE)


if __name__ == "__main__":
    unittest.main()
