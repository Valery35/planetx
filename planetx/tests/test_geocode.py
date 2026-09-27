# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Поиск места через Nominatim: адрес запроса и разбор ответа."""
import os
import sys
import unittest
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import geocode as gc  # noqa: E402

# Сокращённый ответ Nominatim jsonv2 на запрос «Пермь».
PERM = [
    {"lat": "58.0103211", "lon": "56.2341778", "name": "Пермь",
     "display_name": "Пермь, городской округ Пермь, Пермский край, "
                     "Приволжский федеральный округ, Россия",
     "boundingbox": ["57.8637", "58.1766", "55.8046", "56.6573"]},
    {"lat": "59.3", "lon": "56.6", "name": "Пермский край",
     "display_name": "Пермский край, Россия",
     "boundingbox": ["56.1", "61.6", "51.8", "59.6"]},
    {"lon": "1.0", "name": "без широты"},
]


class TestUrl(unittest.TestCase):

    def query(self, url):
        return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}

    def test_query_and_language(self):
        q = self.query(gc.search_url("  Пермь   край ", "ru"))
        self.assertEqual(q["q"], "Пермь край")
        self.assertEqual(q["accept-language"], "ru")
        self.assertEqual(q["format"], "jsonv2")
        self.assertEqual(q["limit"], str(gc.SEARCH_LIMIT))

    def test_local_names_send_no_language(self):
        self.assertNotIn("accept-language",
                         self.query(gc.search_url("Perm", None)))

    def test_goes_to_nominatim(self):
        self.assertTrue(gc.search_url("x").startswith(gc.NOMINATIM + "?"))


class TestParse(unittest.TestCase):

    def test_places_in_answer_order(self):
        places = gc.parse_places(PERM)
        self.assertEqual([p.name for p in places],
                         ["Пермь", "Пермский край"])

    def test_detail_drops_name(self):
        perm = gc.parse_places(PERM)[0]
        self.assertTrue(perm.detail.startswith("городской округ Пермь"))
        self.assertEqual(gc.place_text(perm).split(", ")[0], "Пермь")

    def test_box_is_west_south_east_north(self):
        perm = gc.parse_places(PERM)[0]
        self.assertEqual(perm.box, (55.8046, 57.8637, 56.6573, 58.1766))
        self.assertAlmostEqual(perm.lat, 58.0103211)

    def test_bad_answers(self):
        self.assertEqual(gc.parse_places(None), [])
        self.assertEqual(gc.parse_places({"error": "x"}), [])
        broken = [{"lat": "1", "lon": "2", "display_name": "A, B",
                   "boundingbox": ["x"]}]
        place = gc.parse_places(broken)[0]
        self.assertEqual((place.name, place.detail, place.box),
                         ("A", "B", None))


if __name__ == "__main__":
    unittest.main()
