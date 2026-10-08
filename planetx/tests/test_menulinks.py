# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/menulinks.py: свои пункты меню на глобусе."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import menulinks as ml  # noqa: E402


class TestMenuLinks(unittest.TestCase):

    def test_fill_puts_point_and_zoom(self):
        url = ml.fill("https://example.org/?q={lat},{lon}&z={zoom}",
                      58.0105, 56.2294, 12.6)
        self.assertEqual(url,
                         "https://example.org/?q=58.010500,56.229400&z=12")
        url = ml.fill(ml.EXAMPLE[1], 1.5, -2.25, 9)
        self.assertTrue(url.startswith("https://embed.windy.com/"))
        self.assertIn("metricTemp=%C2%B0C", url)
        self.assertIn("&zoom=9&lat=1.500000&lon=-2.250000"
                      "&detailLat=1.500000&detailLon=-2.250000", url)

    def test_check_names_the_reason(self):
        good = "https://example.org/{lat}/{lon}"
        self.assertEqual(ml.check("Пример", good), "")
        self.assertEqual(ml.check(" ", good), "name")
        self.assertEqual(ml.check("Пример", "ftp://x/{lat}/{lon}"), "scheme")
        self.assertEqual(ml.check("Пример", "file:///{lat}/{lon}"), "scheme")
        self.assertEqual(ml.check("Пример", "https://x/{lat}"), "place")
        self.assertEqual(ml.check("Пример", "https://x/{lat}/{lon}/{alt}"),
                         "braces")
        self.assertEqual(ml.check("Пример", "https://x/{lat}/{lon}/{"),
                         "braces")

    def test_settings_round_trip_skips_bad_items(self):
        items = [("Windy", ml.EXAMPLE[1]), ("Карта", "https://x/{lat}/{lon}")]
        self.assertEqual(ml.load(ml.dump(items)), items)
        text = ml.dump(items + [("Плохой", "javascript:{lat}{lon}")])
        self.assertEqual(ml.load(text), items)
        self.assertEqual(ml.load("{не json"), [])
        self.assertEqual(ml.load('{"a": 1}'), [])
        self.assertEqual(ml.load(""), [])


if __name__ == "__main__":
    unittest.main()
