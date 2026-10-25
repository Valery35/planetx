# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Облака точек лидара по сети: запросы и разбор каталогов IGN и 3DEP,
выбор плиток у точки, ключ SAS."""
import json
import os
import sys
import unittest
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import lidarnet  # noqa: E402

# Ответ WFS IGN у Гренобля 25 октября 2026 года, сокращён.
IGN = {"type": "FeatureCollection", "features": [
    {"geometry": {"type": "MultiPolygon", "coordinates": [[[
        [5.70086541, 45.20668645], [5.71359534, 45.2063778],
        [5.71315777, 45.19737892], [5.70042989, 45.19768752],
        [5.70086541, 45.20668645]]]]},
     "properties": {"coordonnees_nw": "0912-6460",
                    "nombre_points": 16072567,
                    "date_debut_acquisition": "2023-09-27Z",
                    "url_npl": "http://data.geopf.fr/telechargement/"
                               "download/LiDARHD-NUALID/x/"
                               "LHD_FXX_0912_6460_PTS_LAMB93_IGN69.copc.laz"}},
    {"geometry": {"type": "Polygon", "coordinates": [[
        [5.71315777, 45.19737892], [5.7258855, 45.19706887],
        [5.72544602, 45.18807005], [5.71315777, 45.19737892]]]},
     "properties": {"coordonnees_nw": "0913-6459", "nombre_points": 9,
                    "url_npl": "https://data.geopf.fr/x/b.copc.laz"}},
    {"geometry": None, "properties": {"url_npl": "https://x/c.copc.laz"}}]}
# Запись поиска STAC 3dep-lidar-copc, рамка с отметками.
PC = {"features": [{
    "id": "USGS_LPC_UT_StatewideSouth_2020_A20_12SUH7021",
    "bbox": [-112.48332701, 38.12750163, 2475.74, -112.48220744,
             38.13247722, 2754.14],
    "assets": {"data": {"href": "https://usgslidareuwest.blob.core."
                                "windows.net/usgs-3dep-copc/usgs-copc/a/"
                                "copc/x.copc.laz"}},
    "properties": {"pc:count": 376166,
                   "start_datetime": "2020-01-01T00:00:00Z"}}]}


class TestLidarNet(unittest.TestCase):
    def test_ign_request_and_parse(self):
        box = lidarnet.box_around(45.19, 5.725)
        query = parse_qs(urlparse(lidarnet.ign_url(box)).query)
        south, west, north, east = (float(v) for v in
                                    query["BBOX"][0].split(",")[:4])
        self.assertLess(south, 45.19)
        self.assertGreater(east, 5.725)
        self.assertAlmostEqual((north - south) * 111320.0, lidarnet.SIDE,
                               delta=1.0)
        tiles = lidarnet.parse_ign(json.dumps(IGN).encode())
        self.assertEqual([t.name for t in tiles],
                         ["LiDAR HD 0912-6460", "LiDAR HD 0913-6459"])
        self.assertTrue(tiles[0].url.startswith("https://data.geopf.fr/"))
        self.assertEqual(tiles[0].date, "2023-09-27")
        self.assertEqual(tiles[0].points, 16072567)
        self.assertAlmostEqual(tiles[0].box[0], 5.70042989)

    def test_pc_parse_and_key(self):
        body = lidarnet.pc_body((1.0, 2.0, 3.0, 4.0))
        self.assertEqual(body["collections"], [lidarnet.PC_COLLECTION])
        tiles = lidarnet.parse_pc(PC)
        self.assertEqual(len(tiles), 1)
        tile = tiles[0]
        self.assertEqual(tile.box, (-112.48332701, 38.12750163,
                                    -112.48220744, 38.13247722))
        self.assertEqual((tile.points, tile.date), (376166, "2020"))
        self.assertTrue(lidarnet.needs_key(tile.url))
        keyed = lidarnet.with_key(tile.url, "sv=1&sig=a")
        self.assertTrue(keyed.endswith(".copc.laz?sv=1&sig=a"))
        self.assertEqual(lidarnet.with_key(keyed, "sv=2"),
                         tile.url + "?sv=2")
        ign = "https://data.geopf.fr/x/b.copc.laz"
        self.assertFalse(lidarnet.needs_key(ign))
        self.assertEqual(lidarnet.with_key(ign, "sv=2"), ign)

    def test_choose_covering_first(self):
        tiles = lidarnet.parse_ign(IGN)
        found = lidarnet.choose(tiles + tiles, 45.193, 5.718, limit=4)
        self.assertEqual([t.name for t in found],
                         ["LiDAR HD 0913-6459", "LiDAR HD 0912-6460"])
        self.assertEqual(len(lidarnet.choose(tiles, 45.2, 5.71, 1)), 1)


if __name__ == "__main__":
    unittest.main()
