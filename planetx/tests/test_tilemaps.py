# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Карты картинками: прозрачный цвет «нет данных», значение по цвету
пикселя, запрос и ответ GetFeatureInfo SoilGrids."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import glim  # noqa: E402
import tilemaps  # noqa: E402

# Ответ GetFeatureInfo SoilGrids у Перми 17 октября 2026 года.
ANSWER = (b'<html><body><b>Value: </b><span id="value">250</span><br>'
          b'<b>Query Layer: </b><span id="value">clay_0-5cm_mean</span>'
          b'</body></html>')


class TestTileMaps(unittest.TestCase):
    def test_every_key_has_map(self):
        self.assertEqual(set(tilemaps.KEYS), set(tilemaps.MAPS))
        for key, tmap in tilemaps.MAPS.items():
            self.assertEqual(tmap.key, key)
            self.assertTrue(tmap.stops is not None or tmap.classes)
            self.assertTrue("{bbox}" in tmap.url if tmap.wms
                            else "{z}" in tmap.url)

    def test_white_of_soil_map_is_clear(self):
        tile = np.full((2, 2, 4), 255, np.uint8)
        clay = tilemaps.MAPS["soil_clay"]
        self.assertIsNone(tilemaps.rgba(clay, tile))
        tile[0, 0, :3] = (201, 140, 80)
        out = tilemaps.rgba(clay, tile, opacity=0.5)
        self.assertEqual(out[0, 0, 3], 128)
        self.assertEqual(out[0, 0, 0], round(201 * 0.5))
        self.assertEqual(out[1, 1, 3], 0)

    def test_empty_tile_is_none(self):
        water = tilemaps.MAPS["water_transitions"]
        self.assertIsNone(tilemaps.rgba(water, np.zeros((4, 4, 4),
                                                        np.uint8)))

    def test_class_by_pixel_colour(self):
        lith = tilemaps.MAPS["glim"]
        color = dict((c, rgb) for c, _, rgb in glim.CLASSES)["sc"]
        self.assertEqual(tilemaps.value_of(lith, color + (255,)), "sc")
        self.assertIsNone(tilemaps.value_of(lith, color + (0,)))
        water = tilemaps.MAPS["water_transitions"]
        self.assertEqual(tilemaps.value_of(water, (208, 47, 60, 255)),
                         "lost_permanent")
        self.assertIsNone(tilemaps.value_of(water, (60, 60, 60, 255)))

    def test_water_occurrence_is_blue_share(self):
        water = tilemaps.MAPS["water_occurrence"]
        self.assertEqual(tilemaps.value_of(water, (2, 0, 252, 252)), 99)
        self.assertEqual(tilemaps.value_of(water, (237, 0, 17, 18)), 7)

    def test_worldcover_coarse_levels_from_terrain(self):
        cover = tilemaps.MAPS["worldcover"]
        coarse = tilemaps.tile_url(cover, cover.url, 5, 20, 9)
        self.assertTrue(coarse.endswith("worldcover/5/20/9.png"))
        fine = tilemaps.tile_url(cover, cover.url, 6, 41, 19)
        self.assertIn("planetarycomputer", fine)
        self.assertIn("/6/41/19@1x", fine)
        self.assertEqual(tilemaps.value_of(cover, (240, 150, 255, 255)),
                         "crop")
        # У карты без coarse один шаблон на все уровни.
        lith = tilemaps.MAPS["glim"]
        self.assertTrue(tilemaps.tile_url(lith, lith.url, 2, 1, 1)
                        .endswith("glim/2/1/1.png"))

    def test_soil_query(self):
        clay = tilemaps.MAPS["soil_clay"]
        url = tilemaps.query_url(clay, 58.0, 56.25)
        self.assertIn("BBOX=56.24400,57.99400,56.25600,58.00600", url)
        self.assertIn("QUERY_LAYERS=clay_0-5cm_mean", url)
        self.assertAlmostEqual(tilemaps.parse_query(clay, ANSWER), 25.0)
        self.assertIsNone(tilemaps.parse_query(clay, b"<html></html>"))
        self.assertIsNone(tilemaps.query_url(tilemaps.MAPS["glim"], 0, 0))


if __name__ == "__main__":
    unittest.main()
