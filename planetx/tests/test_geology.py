# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Геологическая карта Macrostrat: пустые тайлы, ответ о породе."""
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import geology  # noqa: E402

# Ответ map_query у Перми 17 октября 2026 года, сокращён.
ANSWER = {"success": {"v": 2, "license": "CC-BY 4.0", "data": {
    "elevation": 166, "burwell": [{
        "map_id": 3154618, "name": "East European plate", "strat_name": "",
        "lith": "clay", "descrip": "", "comments": "",
        "t_int_name": "Late Permian", "t_int_age": 251.902,
        "b_int_name": "Late Permian", "b_int_age": 274.4,
        "color": "#FBA794", "scale": "medium",
        "ref": {"name": "Europe 1:5M", "authors": "Asch, K.",
                "ref_year": "2003",
                "url": "https://www.bgr.bund.de/igme5000"}}],
    "macrostrat": {}, "lines": {}}}}


class TestGeology(unittest.TestCase):
    def test_empty_tile_is_none(self):
        self.assertIsNone(geology.rgba(np.zeros((4, 4, 4), np.uint8)))

    def test_premultiplied(self):
        tile = np.zeros((2, 2, 4), np.uint8)
        tile[0, 0] = (200, 100, 50, 255)
        out = geology.rgba(tile, opacity=0.5)
        self.assertEqual(tuple(out[0, 0]), (100, 50, 25, 128))
        self.assertEqual(tuple(out[1, 1]), (0, 0, 0, 0))

    def test_parse_query(self):
        units = geology.parse_query(json.dumps(ANSWER).encode("utf-8"))
        self.assertEqual(len(units), 1)
        unit = units[0]
        self.assertEqual(unit["name"], "East European plate")
        self.assertEqual(unit["lith"], "clay")
        self.assertEqual(unit["source"], "Europe 1:5M")
        self.assertEqual(geology.age_text(unit),
                         ("Late Permian", "274.4-251.9"))
        unit = dict(unit, bottom="Early Permian", top_age=None)
        self.assertEqual(geology.age_text(unit),
                         ("Early Permian - Late Permian", ""))
        empty = {"success": {"data": {"burwell": []}}}
        self.assertEqual(geology.parse_query(json.dumps(empty)), [])
        # Глубже карты места - запись {} у Перми на уровне 10.
        deep = {"success": {"data": {"burwell": [{}]}}}
        self.assertEqual(geology.parse_query(json.dumps(deep)), [])

    def test_coarser(self):
        self.assertEqual(geology.coarser(13), 10)
        self.assertEqual(geology.coarser(3), 1)
        self.assertIsNone(geology.coarser(1))

    def test_urls(self):
        url = geology.query_url(58.0, 56.25, 8.4)
        self.assertIn("lat=58.00000", url)
        self.assertIn("lng=56.25000", url)
        self.assertTrue(url.endswith("&z=8"))
        self.assertTrue(geology.query_url(0, 0, 30).endswith("&z=16"))
        self.assertIn("{z}", geology.TILES)


if __name__ == "__main__":
    unittest.main()
