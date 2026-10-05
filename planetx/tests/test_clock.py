# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/clock.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import clock  # noqa: E402

NOW = 1.8e9


class TestExtent(unittest.TestCase):

    def test_clock_alone_is_window_around_moment(self):
        self.assertEqual(clock.extent(None, NOW),
                         (NOW - clock.HALF, NOW + clock.HALF))

    def test_without_clock_data_extent_only(self):
        self.assertIsNone(clock.extent(None, NOW, on=False))
        self.assertEqual(clock.extent((1.0, 2.0), NOW, on=False), (1.0, 2.0))

    def test_union_with_data_and_left_handle(self):
        lo, hi = clock.extent((NOW - 10 * clock.HALF, NOW - 9 * clock.HALF),
                              NOW, lo=NOW - 5 * clock.HALF)
        self.assertEqual(lo, NOW - 10 * clock.HALF)
        self.assertEqual(hi, NOW + clock.HALF)
        self.assertEqual(clock.window(NOW, NOW - 5 * clock.HALF)[0],
                         NOW - 5 * clock.HALF)


class TestAdvance(unittest.TestCase):

    def test_rate_is_real_time_multiple(self):
        self.assertEqual(clock.shift((0.0, 100.0), 3600.0, 0.04), 144.0)
        # Вся шкала за 20 с: за секунду - двадцатая доля охвата.
        self.assertEqual(clock.shift((0.0, 100.0), None, 1.0), 5.0)

    def test_clock_runs_past_extent(self):
        lo, hi, span, going = clock.advance(NOW, NOW, (NOW - 5, NOW + 5),
                                            10.0, True, False)
        self.assertEqual((lo, hi, span, going), (NOW + 10, NOW + 10, None,
                                                 True))

    def test_data_stops_or_loops_at_end(self):
        self.assertEqual(clock.advance(8.0, 9.0, (0.0, 10.0), 3.0, False,
                                       False), (9.0, 10.0, (0.0, 10.0),
                                                False))
        self.assertEqual(clock.advance(8.0, 9.0, (0.0, 10.0), 3.0, False,
                                       True), (0.0, 1.0, (0.0, 10.0), True))
        self.assertEqual(clock.advance(1.0, 2.0, (0.0, 10.0), 3.0, False,
                                       False), (4.0, 5.0, (0.0, 10.0), True))


if __name__ == "__main__":
    unittest.main()
