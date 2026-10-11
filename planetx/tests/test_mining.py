# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Горные разработки: тайлы вида, запрос Overpass, разбор ответа."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import deposits  # noqa: E402
import mining  # noqa: E402


class TestTiles(unittest.TestCase):

    def test_tile_contains_point(self):
        x, y = mining.tile_of(59.41, 56.80)
        south, west, north, east = mining.tile_bounds(x, y)
        self.assertTrue(south <= 59.41 <= north)
        self.assertTrue(west <= 56.80 <= east)

    def test_view_tiles_near_only(self):
        tiles = mining.view_tiles(59.41, 56.80, 30000.0)
        self.assertEqual(len(tiles), mining.MAX_TILES)
        self.assertEqual(tiles[0], mining.tile_of(59.41, 56.80))
        self.assertEqual(mining.view_tiles(59.41, 56.80, 500000.0), [])


class TestQuery(unittest.TestCase):

    def test_union_of_view_tiles(self):
        tiles = mining.view_tiles(59.41, 56.80, 30000.0)
        box = mining.union(mining.tile_bounds(*t) for t in tiles)
        for t in tiles:
            south, west, north, east = mining.tile_bounds(*t)
            self.assertTrue(box[0] <= south and box[2] >= north)
            self.assertTrue(box[1] <= west and box[3] >= east)
        # Через линию перемены дат - первая рамка.
        self.assertEqual(mining.union([(0, 179, 1, 180), (0, -180, 1, -179)]),
                         (0, 179, 1, 180))

    def test_query_has_all_kinds_and_box(self):
        text = mining.query((59.0, 56.0, 60.0, 57.0))
        self.assertIn('nwr["landuse"="quarry"](59.00000,56.00000,'
                      '60.00000,57.00000);', text)
        self.assertIn('nwr["man_made"="mineshaft"]', text)
        self.assertTrue(text.startswith("[out:json]"))
        self.assertTrue(text.endswith("out center tags;"))

    def test_parse_and_points(self):
        answer = {"elements": [
            {"type": "way", "id": 1, "center": {"lat": 59.4, "lon": 56.8},
             "tags": {"landuse": "quarry", "name": "Карьер",
                      "resource": "sand;gravel"}},
            {"type": "node", "id": 2, "lat": 59.6, "lon": 56.7,
             "tags": {"man_made": "mine", "name:ru": "Рудник СКРУ-1",
                      "name": "SKRU-1", "resource": "potash",
                      "operator": "Уралкалий"}},
            {"type": "way", "id": 1, "center": {"lat": 59.4, "lon": 56.8},
             "tags": {"landuse": "quarry"}},
            {"type": "relation", "id": 3, "tags": {"landuse": "quarry"}}]}
        items = mining.parse(answer)
        self.assertEqual(len(items), 3)  # без середины - пропущен
        self.assertEqual(items[1]["name"], "Рудник СКРУ-1")
        self.assertEqual(items[0]["resource"], "sand, gravel")
        self.assertEqual(items[0]["kind"], "quarry")
        data = mining.to_deposits(items)
        self.assertEqual(len(data), 2)  # повтор way/1 отброшен
        names = [g[0] for g in deposits.GROUPS]
        self.assertEqual(names[data.group[1]], "industrial")  # калий
        fields = data.text(1)
        self.assertEqual(fields[6], "Уралкалий")
        self.assertEqual(fields[9], "node/2")


if __name__ == "__main__":
    unittest.main()
