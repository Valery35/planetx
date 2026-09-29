# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Время меток: разбор строк KML, промежутки, видимость на шкале."""
import calendar
import math
import os
import sys
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import when  # noqa: E402

DAY = calendar.timegm((2026, 9, 30, 0, 0, 0))


class TestParse(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(when.parse("2026-09-30"), DAY)
        self.assertEqual(when.parse("2026-09"),
                         calendar.timegm((2026, 9, 1, 0, 0, 0)))
        self.assertEqual(when.parse("2026"),
                         calendar.timegm((2026, 1, 1, 0, 0, 0)))
        self.assertEqual(when.parse("2026-09-30T12:30:00Z"),
                         DAY + 12.5 * 3600)
        self.assertEqual(when.parse("2026-09-30T12:30:00"),
                         DAY + 12.5 * 3600)
        self.assertEqual(when.parse("2026-09-30T17:30:00+05:00"),
                         DAY + 12.5 * 3600)
        self.assertEqual(when.parse("2026-09-30T12:30:00.5Z"),
                         DAY + 12.5 * 3600 + 0.5)

    def test_bad(self):
        for text in ("", None, "вчера", "2026-13-01", "2026-09-30T25"):
            self.assertIsNone(when.parse(text), text)

    def test_text_round_trip(self):
        self.assertEqual(when.parse(when.text(DAY + 3661)), DAY + 3661)


class TestIntervals(unittest.TestCase):
    def test_stamp_and_span(self):
        self.assertEqual(when.interval(("2026-09-30", "2026-09-30")),
                         (DAY, DAY))
        lo, hi = when.interval(("2026-09-30", ""))
        self.assertEqual(lo, DAY)
        self.assertEqual(hi, math.inf)
        self.assertIsNone(when.interval(None))
        self.assertIsNone(when.interval(("", "")))

    def test_visible(self):
        span = ("2026-09-01", "2026-09-30")
        self.assertTrue(when.visible(span, DAY - 86400, DAY + 86400))
        self.assertFalse(when.visible(span, DAY + 86400, DAY + 2 * 86400))
        # Метка без времени видна всегда.
        self.assertTrue(when.visible(None, 0.0, 1.0))

    def test_extent(self):
        times = [("2026-09-01", "2026-09-10"), None, ("2026-10-05",) * 2,
                 ("", "2026-08-01")]
        lo, hi = when.extent(times)
        self.assertEqual(lo, calendar.timegm((2026, 8, 1, 0, 0, 0)))
        self.assertEqual(hi, calendar.timegm((2026, 10, 5, 0, 0, 0)))
        self.assertIsNone(when.extent([None, ("", "")]))

    def test_pack(self):
        for time in (("2026-09-30", "2026-09-30"), ("2026", "2027"),
                     ("", "2026-09-30"), ("2026-09-30T12:00:00Z", "")):
            self.assertEqual(when.unpack(when.pack(time)), time)
        self.assertEqual(when.pack(None), "")
        self.assertIsNone(when.unpack(""))


if __name__ == "__main__":
    unittest.main()
