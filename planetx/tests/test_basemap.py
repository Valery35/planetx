# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подложки из подключений XYZ QGIS."""
import os
import sys
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import basemap as bm  # noqa: E402

ESRI = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}")
TERRARIUM = ("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
             "{z}/{x}/{y}.png")

# Подключения, как их показал QGIS 4.0.3 26 сентября 2026 года,
# и Esri World Imagery.
SETTINGS = {
    "OpenStreetMap": {"url": bm.OSM_URL, "zmin": "0", "zmax": "19",
                      "http-header": {}, "referer": "", "authcfg": ""},
    "Mapzen Global Terrain": {"url": TERRARIUM, "zmin": "0", "zmax": "15",
                              "interpretation": "terrariumterrain"},
    "Esri World Imagery": {"url": ESRI, "zmin": "0", "zmax": "18"},
}


class TestUrl(unittest.TestCase):

    def test_xyz(self):
        self.assertEqual(bm.tile_url(ESRI, 3, 5, 2),
                         ESRI.replace("{z}/{y}/{x}", "3/2/5"))

    def test_tms(self):
        # {-y} считает строки снизу: на уровне 3 строка 2 сверху - 5 снизу.
        self.assertEqual(bm.tile_url("t/{z}/{x}/{-y}", 3, 1, 2), "t/3/1/5")

    def test_quadkey(self):
        # Пример из описания системы тайлов Bing Maps.
        self.assertEqual(bm.quadkey(3, 3, 5), "213")
        self.assertEqual(bm.tile_url("q/{q}.jpg", 3, 3, 5), "q/213.jpg")
        self.assertEqual(bm.quadkey(0, 0, 0), "")

    def test_valid(self):
        self.assertTrue(bm.valid_url(ESRI))
        self.assertTrue(bm.valid_url("a/{q}"))
        self.assertTrue(bm.valid_url("a/{z}/{x}/{-y}"))
        self.assertFalse(bm.valid_url("a/{z}/{x}"))
        self.assertFalse(bm.valid_url("a/{z}/{x}/{y}/{switch:a,b}"))
        self.assertFalse(bm.valid_url("a/b.png"))


class TestSettings(unittest.TestCase):

    def test_list(self):
        sources = bm.from_settings(SETTINGS)
        self.assertEqual([s.name for s in sources], ["Esri World Imagery"])
        esri = sources[0]
        self.assertEqual(esri.max_level, 18)
        self.assertIn("Esri", esri.attribution[0])
        self.assertEqual(esri.parallel, bm.OTHER_PARALLEL)

    def test_terrain_skipped(self):
        names = [s.name for s in bm.from_settings(SETTINGS)]
        self.assertNotIn("Mapzen Global Terrain", names)

    def test_levels(self):
        items = {
            "deep": {"url": "a/{z}/{x}/{y}", "zmax": "23"},
            "empty": {"url": "b/{z}/{x}/{y}", "zmax": ""},
            "shallow": {"url": "c/{z}/{x}/{y}", "zmax": "1"},
            "late": {"url": "d/{z}/{x}/{y}", "zmin": "5"},
        }
        levels = {s.name: s.max_level for s in bm.from_settings(items)}
        self.assertEqual(levels, {"deep": bm.MAX_LEVEL,
                                  "empty": bm.DEFAULT_MAX})

    def test_headers(self):
        items = {"x": {"url": "a/{z}/{x}/{y}", "referer": "https://r/",
                       "http-header": {"X-Key": "1", "Empty": ""}}}
        source = bm.from_settings(items)[0]
        self.assertEqual(source.headers,
                         {"X-Key": "1", "Referer": "https://r/"})
        self.assertEqual(source.attribution, ("x", ""))

    def test_login(self):
        items = {"with": {"url": "a/{z}/{x}/{y}", "username": "u",
                          "password": "p"},
                 "without": {"url": "b/{z}/{x}/{y}", "username": "",
                             "password": ""}}
        sources = {s.name: s for s in bm.from_settings(items)}
        self.assertEqual((sources["with"].username,
                          sources["with"].password), ("u", "p"))
        self.assertIsNone(sources["without"].username)

    def test_osm(self):
        source = bm.osm()
        self.assertTrue(source.builtin)
        self.assertEqual(source.parallel, bm.OSM_PARALLEL)
        self.assertEqual(source.tile_url(1, 0, 1),
                         "https://tile.openstreetmap.org/1/0/1.png")


if __name__ == "__main__":
    unittest.main()
