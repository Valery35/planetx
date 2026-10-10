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


LANDSAT = ("https://landsateuwest.blob.core.windows.net/landsat-c2/level-2/"
           "standard/oli-tirs/2025/166/020/LC09_L2SP_166020_20250923_"
           "20250924_02_T1/LC09_L2SP_166020_20250923_20250924_02_T1_")


def landsat_item(platform="landsat-9", thermal="lwir11"):
    optical = {"scale": 2.75e-05, "offset": -0.2, "nodata": 0,
               "spatial_resolution": 30}
    keys = ("blue", "green", "red", "nir08", "swir16", "swir22")
    assets = {k: {"href": LANDSAT + k + ".TIF", "raster:bands": [optical]}
              for k in keys}
    assets[thermal] = {"href": LANDSAT + "ST_B10.TIF", "raster:bands": [
        {"scale": 0.00341802, "offset": 149, "nodata": 0}]}
    assets["qa_pixel"] = {"href": LANDSAT + "QA_PIXEL.TIF",
                          "raster:bands": [{"nodata": 1}]}
    assets["rendered_preview"] = {
        "href": "https://planetarycomputer.microsoft.com/api/data/v1/item/"
                "preview.png?collection=landsat-c2-l2&item=x"}
    return {"id": "LC09_L2SP_166020_20250923_02_T1",
            "properties": {"datetime": "2025-09-23T07:14:45.55Z",
                           "platform": platform, "proj:epsg": 32640,
                           "eo:cloud_cover": 24.97,
                           "view:sun_elevation": 31.7,
                           "landsat:wrs_path": "166",
                           "landsat:wrs_row": "020"},
            "assets": assets}


class TestSide(unittest.TestCase):
    def test_side_follows_view_within_limits(self):
        self.assertEqual(s2.side_for_view(16240.0), 16.2)
        self.assertEqual(s2.side_for_view(300.0), s2.SIDE_MIN)
        self.assertEqual(s2.side_for_view(5e6), s2.SIDE_MAX)


class TestLandsat(unittest.TestCase):
    def test_item(self):
        s = s2.parse_item(landsat_item())
        self.assertEqual(s.mission, "landsat")
        self.assertEqual(s.tile, "L9 166/020")
        self.assertEqual(s.epsg, 32640)
        self.assertEqual(s.when, "2025-09-23 07:14")
        self.assertIn("preview.png", s.thumbnail)
        self.assertAlmostEqual(s.assets["red"].offset, -0.2)
        # Тепловой канал Landsat 8-9 доступен под общим ключом lwir.
        self.assertEqual(s.assets["lwir"].href, s.assets["lwir11"].href)
        self.assertAlmostEqual(s.assets["lwir"].offset, 149.0)

    def test_old_landsat_thermal(self):
        s = s2.parse_item(landsat_item("landsat-5", "lwir"))
        self.assertEqual(s.tile, "L5 166/020")
        self.assertIn("lwir", s.assets)

    def test_search_body(self):
        body = s2.search_body({"type": "Point", "coordinates": [56, 58]},
                              "1990-01-01", "1990-12-31", 50,
                              mission="landsat")
        self.assertEqual(body["collections"], ["landsat-c2-l2"])
        self.assertEqual(s2.SEARCHES["landsat"], s2.LANDSAT_SEARCH)

    def test_qa_clouds(self):
        # Чистый 21824, облако 22280 (биты 3 и 1), тень 23888 (бит 4),
        # нет данных 1 (бит 0).
        qa = np.array([[21824, 22280], [23888, 1]], dtype=np.uint16)
        inside = np.ones((2, 2), dtype=bool)
        cloud, valid = s2.cloud_share_qa(qa, inside)
        self.assertAlmostEqual(cloud, 200.0 / 3.0)
        self.assertAlmostEqual(valid, 75.0)
        scene = s2.parse_item(landsat_item())
        clear = s2.clear_mask(scene, qa)
        self.assertEqual(clear.tolist(), [[True, False], [False, False]])

    def test_products_use_nir08(self):
        self.assertEqual(s2.needed(["infrared", "ndvi"], "landsat"),
                         ["nir08", "red", "green"])
        self.assertEqual(s2.needed(["lst"], "landsat"), ["lwir"])
        self.assertIn("lst", s2.products_of("landsat"))
        self.assertNotIn("lst", s2.products_of("sentinel2"))
        bands = {"nir08": np.full((1, 1), 0.4, np.float32),
                 "red": np.full((1, 1), 0.1, np.float32)}
        self.assertAlmostEqual(float(s2.product("ndvi", bands,
                                                "landsat")[0, 0]), 0.6, 5)

    def test_surface_temperature(self):
        scene = s2.parse_item(landsat_item())
        kelvin = s2.reflectance(np.array([[0, 43636]], dtype=np.uint16),
                                scene.assets["lwir"])
        lst = s2.product("lst", {"lwir": kelvin}, "landsat")
        self.assertTrue(np.isnan(lst[0, 0]))
        # 43636 * 0.00341802 + 149 = 298.15 K = 25 °C.
        self.assertAlmostEqual(float(lst[0, 1]), 25.0, 1)

    def test_names_and_credit(self):
        s = s2.parse_item(landsat_item())
        self.assertEqual(s2.file_name(s, "ndvi"), "L9_20250923_166-020_ndvi")
        self.assertEqual(s2.credit(s), "Landsat 9 image courtesy of the "
                                       "U.S. Geological Survey")
        self.assertEqual(s2.step_for([(0, 0), (3000, 3000)], "landsat"),
                         30.0)

    def test_sign(self):
        self.assertEqual(s2.sign("https://a/b.TIF", "st=1&sig=2"),
                         "https://a/b.TIF?st=1&sig=2")
        self.assertEqual(s2.sign("https://a/b.TIF?x=1", "sig=2"),
                         "https://a/b.TIF?x=1&sig=2")
        self.assertEqual(s2.sign("https://a/b.TIF", ""), "https://a/b.TIF")


if __name__ == "__main__":
    unittest.main()
