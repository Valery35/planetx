# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Архив снимков Esri Wayback: выпуски, тайлы, цепочка изменений."""
import datetime
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import themes  # noqa: E402
import wayback as wb  # noqa: E402

TILE = ("https://wayback.maptiles.arcgis.com/arcgis/rest/services/"
        "World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/{}/"
        "{{level}}/{{row}}/{{col}}")
CONFIG = json.dumps({
    "63116": {"itemTitle": "World Imagery (Wayback 2026-09-24)",
              "itemURL": TILE.format(63116),
              "metadataLayerUrl": "https://metadata.example/2026_r09/"
                                  "MapServer"},
    "22252": {"itemTitle": "World Imagery (Wayback 2020-03-11)",
              "itemURL": TILE.format(22252), "metadataLayerUrl": ""},
    "22000": {"itemTitle": "World Imagery (Wayback 2020-03-11)",
              "itemURL": TILE.format(22000), "metadataLayerUrl": ""},
    "10": {"itemTitle": "World Imagery (Wayback 2014-02-20)",
           "itemURL": TILE.format(10), "metadataLayerUrl": ""},
    "bad": {"itemTitle": "World Imagery (Wayback 2015-01-01)"}})
# Ответы tilemap у Перми 18 октября 2026 года.
TILEMAP_NEW = (b'{"data":[1],"location":{"height":1,"left":21612,'
               b'"top":9449,"width":1},"select":[22252],"size":[21325],'
               b'"valid":true}')
TILEMAP_OWN = (b'{"data":[1],"location":{"height":1,"left":21612,'
               b'"top":9449,"width":1},"size":[13041],"valid":true}')
METADATA = json.dumps({"features": [{"attributes": {
    "SRC_DATE2": 1747180800000, "NICE_DESC": "Vantor", "SRC_DESC": "LG02",
    "SRC_RES": 0.34, "SRC_ACC": 8.47}}]})


class TestReleases(unittest.TestCase):

    def setUp(self):
        self.releases = wb.parse_config(CONFIG)

    def test_config_sorted_by_day_one_per_day(self):
        self.assertEqual([r.number for r in self.releases],
                         [10, 22252, 63116])
        self.assertEqual(self.releases[-1].day, datetime.date(2026, 9, 24))
        self.assertTrue(self.releases[-1].meta.endswith("MapServer"))

    def test_intervals_drive_theme_days(self):
        found = wb.intervals(self.releases)
        self.assertEqual(themes.days(found),
                         ["2014-02-20", "2020-03-11", "2026-09-24"])
        moment = wb.moment(datetime.date(2021, 6, 1))
        self.assertEqual(themes.pick_day(found, moment), "2020-03-11")
        self.assertEqual(themes.pick_day(found), "2026-09-24")

    def test_tile_url_keeps_loader_places(self):
        url = wb.tile_url(63116)
        self.assertTrue(url.endswith("/tile/63116/{z}/{y}/{x}"))

    def test_tilemap_and_change_chain(self):
        self.assertEqual(wb.parse_tilemap(TILEMAP_NEW, 63116), 22252)
        self.assertEqual(wb.parse_tilemap(TILEMAP_OWN, 10), 10)
        self.assertIsNone(wb.parse_tilemap(b'{"data":[0]}', 10))
        # Тайл новейшего выпуска - из 22252, следующий запрос - старше.
        nxt = wb.changes_next(self.releases, 22252)
        self.assertEqual(nxt.number, 10)
        self.assertIsNone(wb.changes_next(self.releases, 10))

    def test_tile_of(self):
        self.assertEqual(wb.tile_of(0.0, 0.0, 1), (1, 1))
        self.assertEqual(wb.tile_of(60.0, -170.0, 2), (0, 1))

    def test_search_level_follows_view_width(self):
        self.assertEqual(wb.search_level(600.0), wb.LOCAL_LEVEL)
        self.assertEqual(wb.search_level(2000.0), 15)
        self.assertEqual(wb.search_level(2.0e6), 5)
        self.assertEqual(wb.search_level(4.0e7), 2)

    def test_theme_release_and_url(self):
        theme = themes.BY_KEY[themes.WAYBACK]
        saved = theme.releases
        try:
            theme.releases = {}
            self.assertEqual(theme.url("2020-01-01"), wb.CURRENT_URL)
            theme.releases = wb.by_day(self.releases)
            self.assertEqual(theme.release("2021-06-01").number, 22252)
            self.assertEqual(theme.release("2010-01-01").number, 10)
            self.assertIn("/tile/63116/", theme.url("2026-09-24"))
            self.assertEqual(theme.domains_url(), wb.CONFIG_URL)
        finally:
            theme.releases = saved
        self.assertIn("archive", themes.GROUPS)
        self.assertIn(themes.WAYBACK, [k for k, _, _ in
                                       themes.gallery_items()])

    def test_metadata(self):
        self.assertEqual(wb.metadata_layer(23), 0)
        self.assertEqual(wb.metadata_layer(16), 7)
        self.assertEqual(wb.metadata_layer(5), 13)
        url = wb.metadata_url(self.releases[-1], 58.01, 56.25, 16)
        self.assertIn("/MapServer/7/query?geometry=56.2500000,58.0100000",
                      url)
        self.assertIsNone(wb.metadata_url(self.releases[0], 0, 0, 16))
        info = wb.parse_metadata(METADATA)
        self.assertEqual(info["date"], "2025-05-14")
        self.assertEqual(info["provider"], "Vantor")
        self.assertAlmostEqual(info["resolution"], 0.34)
        self.assertIsNone(wb.parse_metadata(b'{"features":[]}'))


if __name__ == "__main__":
    unittest.main()
