# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/wikipedia.py: адреса, разбор ответов, тайлы, порядок."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import wikipedia as wp  # noqa: E402
from mining import tile_bounds, tile_of  # noqa: E402

ANSWER = {"batchcomplete": "", "query": {"geosearch": [
    {"pageid": 423810, "ns": 0, "title": "Пермская соборная мечеть",
     "lat": 58.014088, "lon": 56.227608, "dist": 184.1, "primary": "",
     "type": "landmark", "dim": 10000},
    {"pageid": 1793088, "ns": 0, "title": "У моста", "lat": 58.0139,
     "lon": 56.2296, "dist": 297.3, "primary": "", "type": None,
     "dim": 200},
    {"pageid": 5, "ns": 0, "title": "Пермь", "lat": 58.0139,
     "lon": 56.2489, "type": "city"},
    {"pageid": 6, "ns": 0, "title": "", "lat": 58.0, "lon": 56.0},
    {"pageid": 7, "ns": 0, "title": "Без точки"}]}}


class TestParse(unittest.TestCase):

    def test_articles_and_rank(self):
        found = wp.parse_geosearch(ANSWER)
        self.assertEqual([a.title for a in found],
                         ["Пермская соборная мечеть", "У моста", "Пермь"])
        self.assertEqual(found[0].rank, wp.TYPE_RANK["landmark"])
        self.assertEqual(found[1].rank, wp.OTHER_RANK)
        self.assertEqual(found[2].rank, wp.TYPE_RANK["city"])
        self.assertAlmostEqual(found[0].lat, 58.014088)

    def test_service_error_is_value_error(self):
        with self.assertRaises(ValueError):
            wp.parse_geosearch({"error": {"code": "toobig",
                                          "info": "Bounding box is too big"}})
        with self.assertRaises(ValueError):
            wp.parse_geosearch([])

    def test_summary(self):
        self.assertEqual(wp.parse_summary({"extract": " Пермь - город. "}),
                         "Пермь - город.")
        self.assertEqual(wp.parse_summary(
            {"extract": "Центральный  — микрорайон."}),
            "Центральный — микрорайон.")
        with self.assertRaises(ValueError):
            wp.parse_summary({"type": "not_found"})


class TestUrls(unittest.TestCase):

    def test_bbox_is_tile_north_west_south_east(self):
        tile = tile_of(58.01, 56.23, wp.ZOOM)
        url = wp.geosearch_url("ru", tile)
        south, west, north, east = tile_bounds(tile[0], tile[1], wp.ZOOM)
        self.assertTrue(url.startswith("https://ru.wikipedia.org/w/api.php?"))
        self.assertIn("gsbbox={:.6f}|{:.6f}|{:.6f}|{:.6f}".format(
            north, west, south, east), url)
        self.assertIn("gslimit=500", url)

    def test_tile_is_under_service_limit(self):
        # Служба отвергает рамку 0.18° × 0.18° у экватора (около 400 км²)
        # и принимает 0.16°. Тайл уровня ZOOM у экватора уже 0.16°.
        tile = tile_of(0.0, 30.0, wp.ZOOM)
        south, west, north, east = tile_bounds(tile[0], tile[1], wp.ZOOM)
        self.assertLess(north - south, 0.16)
        self.assertLess(east - west, 0.16)

    def test_titles_are_quoted(self):
        self.assertEqual(
            wp.page_url("en", "Perm Opera and Ballet Theatre"),
            "https://en.wikipedia.org/wiki/Perm_Opera_and_Ballet_Theatre")
        self.assertIn("/page/summary/AC%2FDC",
                      wp.summary_url("en", "AC/DC"))
        self.assertIn("ru.wikipedia.org/wiki/%D0%9F",
                      wp.page_url("ru", "Пермь"))

    def test_language(self):
        self.assertEqual(wp.language("ru"), "ru")
        self.assertEqual(wp.language(""), "en")
        self.assertEqual(wp.language("ru/../x"), "en")


class TestTiles(unittest.TestCase):

    def test_view_tiles_near_and_far(self):
        tiles = wp.view_tiles(58.01, 56.23, 5000.0)
        self.assertEqual(len(tiles), wp.VIEW_TILES)
        self.assertEqual(tiles[0], tile_of(58.01, 56.23, wp.ZOOM))
        self.assertEqual(len(set(tiles)), len(tiles))
        self.assertEqual(wp.view_tiles(58.01, 56.23,
                                       wp.MAX_ALTITUDE + 1.0), [])

    def test_order_rank_then_distance_without_repeats(self):
        a = wp.Article(1, "far city", 58.5, 56.2, 3)
        b = wp.Article(2, "near landmark", 58.01, 56.23, 5)
        c = wp.Article(3, "near city", 58.02, 56.23, 3)
        got = wp.order([a, b, c, b], 58.01, 56.23)
        self.assertEqual([x.pageid for x in got], [3, 1, 2])
        self.assertEqual(len(wp.order([a, b, c], 58.0, 56.0, limit=2)), 2)


if __name__ == "__main__":
    unittest.main()
