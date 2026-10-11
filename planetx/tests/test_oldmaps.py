# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Исторические карты по годам: последняя карта на момент, шаги по годам."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import oldmaps  # noqa: E402
import when  # noqa: E402


def at(year):
    return when.parse(oldmaps.year_time(year)[0])


class TestShown(unittest.TestCase):

    def setUp(self):
        self.entries = [("a1850", "city", at(1850)),
                        ("a1900", "city", at(1900)),
                        ("a1950", "city", at(1950)),
                        ("b1920", "region", at(1920))]

    def test_latest_not_later_than_moment_per_group(self):
        self.assertEqual(oldmaps.shown(self.entries, at(1925)),
                         {"a1900", "b1920"})

    def test_moment_on_map_year_shows_that_map(self):
        self.assertEqual(oldmaps.shown(self.entries, at(1950)),
                         {"a1950", "b1920"})

    def test_before_first_map_nothing(self):
        self.assertEqual(oldmaps.shown(self.entries, at(1800)), set())

    def test_closed_bar_shows_all(self):
        self.assertEqual(oldmaps.shown(self.entries, None),
                         {"a1850", "a1900", "a1950", "b1920"})


class TestStep(unittest.TestCase):

    def test_steps_by_map_years(self):
        moments = [at(1850), at(1900), at(1900), at(1950)]
        self.assertEqual(oldmaps.step(moments, at(1900), 1), at(1950))
        self.assertEqual(oldmaps.step(moments, at(1900), -1), at(1850))
        self.assertEqual(oldmaps.step(moments, at(1925), -1), at(1900))
        self.assertIsNone(oldmaps.step(moments, at(1950), 1))


class TestYear(unittest.TestCase):

    def test_year_text_and_label(self):
        self.assertEqual(oldmaps.year_time(1890), ("1890", "1890"))
        self.assertEqual(oldmaps.year_label(at(1890)), "1890")
        year = oldmaps.parse_year("-500")
        self.assertEqual(oldmaps.year_label(at(year)), "-500")

    def test_parse_year(self):
        self.assertEqual(oldmaps.parse_year(" 1890 "), 1890)
        self.assertIsNone(oldmaps.parse_year(""))
        with self.assertRaises(ValueError):
            oldmaps.parse_year("0")
        with self.assertRaises(ValueError):
            oldmaps.parse_year("около 1890")

    def test_only_stamp_is_map_moment(self):
        self.assertEqual(oldmaps.start(("1890", "1890")), at(1890))
        self.assertIsNone(oldmaps.start(("1890", "1910")))
        self.assertIsNone(oldmaps.start(None))


if __name__ == "__main__":
    unittest.main()
