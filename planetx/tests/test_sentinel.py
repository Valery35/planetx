# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки Sentinel-2: каталог STAC, участок, облачность, продукты."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import sentinel as s2  # noqa: E402
from coords import to_utm  # noqa: E402

BASE = ("https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-"
        "cogs/40/V/DK/2026/9/S2C_40VDK_20260929_0_L2A/")


def item(day="2026-09-29", cloud=12.5):
    band = {"scale": 0.0001, "offset": -0.1, "nodata": 0,
            "spatial_resolution": 10}
    return {
        "id": "S2C_40VDK_{}_0_L2A".format(day.replace("-", "")),
        "properties": {"datetime": day + "T07:43:29.961000Z",
                       "eo:cloud_cover": cloud, "proj:epsg": 32640,
                       "view:sun_elevation": 29.2,
                       "mgrs:utm_zone": 40, "mgrs:latitude_band": "V",
                       "mgrs:grid_square": "DK"},
        "assets": {
            "red": {"href": BASE + "B04.tif", "raster:bands": [band]},
            "nir": {"href": BASE + "B08.tif", "raster:bands": [band]},
            "scl": {"href": BASE + "SCL.tif",
                    "raster:bands": [{"nodata": 0}]},
            "thumbnail": {"href": BASE + "preview.jpg"},
            "cloud": {"href": "s3://sentinel-s2-l2a/qi/CLD_20m.jp2"}}}


class TestCatalog(unittest.TestCase):

    def test_search_body(self):
        body = s2.search_body(s2.geojson(s2.square(58.0, 56.25, 2000)),
                              "2025-10-01", "2026-09-30", 80)
        self.assertEqual(body["collections"], ["sentinel-2-l2a"])
        self.assertEqual(body["datetime"],
                         "2025-10-01T00:00:00Z/2026-09-30T23:59:59Z")
        self.assertEqual(body["query"]["eo:cloud_cover"]["lte"], 80.0)
        ring = body["intersects"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(len(ring), 5)

    def test_parse_page_and_next(self):
        data = {"features": [item(), {"id": "x", "properties": {},
                                      "assets": {}}],
                "links": [{"rel": "next", "body": {"next": "token"}}]}
        scenes, following = s2.parse_page(data)
        self.assertEqual(len(scenes), 1)
        s = scenes[0]
        self.assertEqual((s.when, s.cloud, s.tile, s.epsg),
                         ("2026-09-29 07:43", 12.5, "40VDK", 32640))
        self.assertEqual(s.assets["red"].offset, -0.1)
        # Смещение уже вычтено из значений - второй раз не вычитается.
        applied = item()
        applied["properties"]["earthsearch:boa_offset_applied"] = True
        self.assertEqual(s2.parse_item(applied).assets["red"].offset, 0.0)
        self.assertNotIn("cloud", s.assets)  # адрес s3 не берётся
        self.assertEqual(following, {"next": "token"})
        self.assertIsNone(s2.parse_page({"features": []})[1])


class TestArea(unittest.TestCase):

    def test_square_side_in_metres(self):
        ring = s2.square(58.0, 56.25, 2000.0)
        xy = s2.ring_utm(ring, 32640)
        self.assertAlmostEqual(xy[1][0] - xy[0][0], 2000.0, delta=15.0)
        self.assertAlmostEqual(xy[3][1] - xy[0][1], 2000.0, delta=15.0)
        east, north = to_utm(58.0, 56.25, 40)[2:]
        middle = np.mean(xy, axis=0)
        self.assertAlmostEqual(middle[0], east, delta=5.0)
        self.assertAlmostEqual(middle[1], north, delta=5.0)

    def test_mask_of_triangle(self):
        xy = [(0.0, 0.0), (100.0, 0.0), (0.0, 100.0)]
        box = s2.bounds(xy, 10.0)
        inside = s2.mask(xy, box, 10.0)
        self.assertEqual(inside.shape, (10, 10))
        # Треугольник - половина квадрата, по центрам пикселей 45 из 100.
        self.assertEqual(int(inside.sum()), 45)
        self.assertTrue(inside[-1, 0])   # юго-запад внутри
        self.assertFalse(inside[0, -1])  # северо-восток снаружи

    def test_step_grows_with_area(self):
        self.assertEqual(s2.step_for([(0, 0), (30000, 30000)]), 10.0)
        self.assertEqual(s2.step_for([(0, 0), (60000, 1)]), 20.0)
        self.assertEqual(s2.step_for([(0, 0), (200000, 1)]), 60.0)


class TestCloud(unittest.TestCase):

    def test_cloud_share_over_area(self):
        scl = np.full((10, 10), 4, dtype=np.uint8)  # растительность
        scl[:, :3] = 9   # облака высокой вероятности
        scl[:, 9] = 0    # нет данных
        inside = np.ones((10, 10), dtype=bool)
        cloud, valid = s2.cloud_share(scl, inside)
        self.assertAlmostEqual(cloud, 100.0 * 30 / 90)
        self.assertAlmostEqual(valid, 90.0)
        # Участок справа от облаков - чистый.
        right = np.zeros((10, 10), dtype=bool)
        right[:, 4:9] = True
        self.assertEqual(s2.cloud_share(scl, right), (0.0, 100.0))
        # Числа Python, а не NumPy: их сравнение отдаётся в Qt.
        self.assertIs(type(cloud), float)
        self.assertIs(type(cloud > 10.0), bool)


class TestProducts(unittest.TestCase):

    def test_reflectance_offset_and_nodata(self):
        asset = s2.Asset("x", 0.0001, -0.1, 0, 10)
        out = s2.reflectance(np.array([[0, 1000, 3000]], np.uint16), asset)
        self.assertTrue(np.isnan(out[0, 0]))
        self.assertAlmostEqual(float(out[0, 1]), 0.0, places=6)
        self.assertAlmostEqual(float(out[0, 2]), 0.2, places=6)

    def test_ndvi_and_composite(self):
        bands = {"nir": np.array([[0.5, 0.3]], np.float32),
                 "red": np.array([[0.1, 0.3]], np.float32),
                 "green": np.array([[0.2, 0.2]], np.float32)}
        ndvi = s2.product("ndvi", bands)
        self.assertAlmostEqual(float(ndvi[0, 0]), 0.4 / 0.6, places=5)
        self.assertAlmostEqual(float(ndvi[0, 1]), 0.0, places=6)
        # Малая или отрицательная сумма - не число, а не -700.
        odd = s2.normalized_difference(np.array([0.05, 0.0], np.float32),
                                       np.array([-0.0499, 0.0], np.float32))
        self.assertTrue(np.isnan(odd).all())
        rgb = s2.product("infrared", bands)
        self.assertEqual(rgb.shape, (3, 1, 2))
        self.assertAlmostEqual(float(rgb[0, 0, 0]), 0.5)  # ИК - красным

    def test_needed_bands_once(self):
        self.assertEqual(s2.needed(["natural", "ndvi"]),
                         ["red", "green", "blue", "nir"])
        for name in s2.PRODUCTS:
            self.assertTrue(s2.needed([name]))

    def test_names(self):
        s = s2.parse_item(item())
        self.assertEqual(s2.file_name(s, "ndvi"), "S2_20260929_40VDK_ndvi")
        self.assertEqual(s2.credit(s),
                         "Contains modified Copernicus Sentinel data 2026")


if __name__ == "__main__":
    unittest.main()
