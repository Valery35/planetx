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


class TestBeforeEra(unittest.TestCase):
    # Даты до нашей эры и до 1970 года: calendar и time.gmtime их
    # не брали, метка Пунических войн оставалась без времени.

    def test_matches_calendar(self):
        for date in ((1, 1, 1), (100, 5, 1), (1600, 2, 29), (1969, 12, 31),
                     (2000, 2, 29), (2026, 9, 30)):
            self.assertEqual(
                when.parse("%04d-%02d-%02d" % date),
                calendar.timegm(date + (0, 0, 0)), date)

    def test_year_before_era(self):
        # «-0001» - 1 год до н. э., он идёт сразу перед 1 годом н. э.
        self.assertEqual(when.parse("0001") - when.parse("-0001"),
                         366 * 86400)
        self.assertLess(when.parse("-0264"), when.parse("-0146"))
        self.assertEqual(when.civil(when.parse("-0216-08-02"))[:3],
                         (-215, 8, 2))

    def test_text_round_trip_before_era(self):
        for text in ("-0216-08-02T00:00:00Z", "0044-03-15T12:00:00Z",
                     "1600-02-29T23:59:59Z"):
            self.assertEqual(when.text(when.parse(text)), text)

    def test_span_is_visible(self):
        war = ("-0218", "-0201")
        self.assertTrue(when.visible(war, when.parse("-0216"),
                                     when.parse("-0215")))
        self.assertFalse(when.visible(war, when.parse("-0149"),
                                      when.parse("-0146")))


class TestDeepTime(unittest.TestCase):
    """Годы длиннее четырёх цифр - палеогеография и глубокое время."""

    def test_long_years(self):
        self.assertEqual(when.civil(when.parse("-28000"))[0], -27999)
        self.assertEqual(when.civil(when.parse("12026"))[0], 12026)


class TestShare(unittest.TestCase):

    def test_inside_span(self):
        war = ("-0218", "-0216")
        lo, hi = when.interval(war)
        self.assertEqual(when.share(war, lo), 0.0)
        self.assertEqual(when.share(war, hi), 1.0)
        self.assertAlmostEqual(when.share(war, (lo + hi) / 2.0), 0.5)
        self.assertEqual(when.share(war, hi + 1.0e9), 1.0)

    def test_nothing_to_grow(self):
        for time in (None, ("2026", "2026"), ("2026", "")):
            self.assertEqual(when.share(time, 0.0), 1.0, time)


if __name__ == "__main__":
    unittest.main()
