# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки Sentinel-2: каталог STAC, участок, облачность, продукты."""
import math
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


class TestThermalFill(unittest.TestCase):
    def test_formula_inverts_radiance_and_keeps_usgs(self):
        # Излучение сцены, построенное из 300 К и ε травы, формула
        # обращает обратно. Где USGS дал значение, оно остаётся.
        k1, k2 = s2.THERMAL_K["9"]
        ndvi = 0.7
        eps = float(s2.emissivity(np.array([ndvi]))[0])
        self.assertAlmostEqual(eps, 0.99, places=4)
        black = k1 / (math.exp(k2 / 300.0) - 1.0)
        tau, up, down = 0.8, 1.2, 2.0
        trad = tau * eps * black + up + tau * (1.0 - eps) * down
        red, nir = 0.03, 0.03 * (1 + ndvi) / (1 - ndvi)
        shape = (1, 2)
        bands = {"lwir": np.array([[np.nan, 290.0]], np.float32),
                 "trad": np.full(shape, trad, np.float32),
                 "atran": np.full(shape, tau, np.float32),
                 "urad": np.full(shape, up, np.float32),
                 "drad": np.full(shape, down, np.float32),
                 "red": np.full(shape, red, np.float32),
                 "nir08": np.full(shape, nir, np.float32)}
        kelvin, share = s2.thermal_fill(bands, "9")
        self.assertAlmostEqual(float(kelvin[0, 0]), 300.0, places=2)
        self.assertEqual(float(kelvin[0, 1]), 290.0)
        self.assertAlmostEqual(share, 0.5)
        self.assertIn("trad", s2.needed(["lst"], "landsat", fill=True))
        self.assertNotIn("trad", s2.needed(["lst"], "landsat"))

    def test_emissivity_classes(self):
        eps = s2.emissivity(np.array([-0.3, 0.1, 0.35, 0.8]))
        self.assertEqual([round(float(e), 3) for e in eps],
                         [0.991, 0.973, 0.987, 0.99])


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


class TestAllBands(unittest.TestCase):
    def test_sentinel_all_bands(self):
        keys = s2.ALL_BANDS["sentinel2"]
        data = item()
        files = ("B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08",
                 "B8A", "B09", "B11", "B12")
        for key, name in zip(keys, files):
            data["assets"][key] = {"href": BASE + name + ".tif",
                                   "raster:bands": [{"scale": 0.0001}]}
        s = s2.parse_item(data)
        self.assertIn("all_bands", s2.products_of("sentinel2"))
        self.assertEqual(s2.all_keys(s), list(keys))
        self.assertEqual(s2.band_label(s, "nir08"), "B8A nir08")
        self.assertEqual(s2.band_label(s, "red"), "B4 red")
        self.assertEqual(s2.needed(["all_bands"]), list(keys))
        bands = {k: np.full((1, 1), n, np.float32)
                 for n, k in enumerate(keys)}
        stack = s2.product("all_bands", bands)
        self.assertEqual(stack.shape, (12, 1, 1))
        self.assertEqual(float(stack[8, 0, 0]), 8.0)
        # 30 км на 10 м - 3000 пикселей: с «Всеми каналами» шаг 20 м.
        side = [(0, 0), (30000, 30000)]
        self.assertEqual(s2.step_for(side), 10.0)
        self.assertEqual(s2.step_for(side, products=("all_bands",)), 20.0)

    def test_landsat_without_coastal(self):
        data = landsat_item("landsat-5", "lwir")
        for key, value in data["assets"].items():
            if key in ("blue", "red"):
                value["href"] = LANDSAT + "SR_B{}.TIF".format(
                    1 if key == "blue" else 3)
        data["assets"]["lwir"]["href"] = LANDSAT + "ST_B6.TIF"
        s = s2.parse_item(data)
        self.assertEqual(s2.all_keys(s), ["blue", "green", "red", "nir08",
                                          "swir16", "swir22", "lwir"])
        self.assertEqual(s2.band_label(s, "lwir"), "B6 lwir, K")
        self.assertEqual(s2.band_label(s, "red"), "B3 red")
        self.assertIn("all_bands", s2.products_of("landsat"))
        self.assertNotIn("all_bands", s2.products_of("mss"))


def scene(mission, assets):
    return s2.Scene("x", "2026-04-05 17:08", 0.0, "T", 32611, 60.0, None,
                    {k: s2.Asset(h, 1.0, 0.0, 0, 30) for k, h in
                     assets.items()}, mission)


class TestWhole(unittest.TestCase):
    """Режим «Вся сцена, исходные файлы»: какие файлы скачиваются и какие
    каналы идут в слой-набор."""

    def test_sentinel_bands_then_cloud_mask(self):
        keys = s2.ALL_BANDS["sentinel2"]
        data = item()
        for key in keys:
            data["assets"][key] = {"href": BASE + key + ".tif",
                                   "raster:bands": [{"scale": 0.0001}]}
        s = s2.parse_item(data)
        files = s2.whole_files(s)
        self.assertEqual(files[:12], list(keys))
        self.assertEqual(files[12:], ["scl"])
        bands = s2.whole_bands(s)
        self.assertEqual([b[0] for b in bands], list(keys))
        self.assertTrue(all(b[1] == b[0] and b[2] == 1 for b in bands))

    def test_aster_group_files_split_into_bands(self):
        s = scene("aster", {"VNIR": "v.tif", "TIR": "t.tif"})
        self.assertEqual(s2.whole_files(s), ["VNIR", "TIR"])
        bands = s2.whole_bands(s)
        self.assertEqual([b[0] for b in bands],
                         ["b1", "b2", "b3n", "b10", "b11", "b12", "b13",
                          "b14"])
        self.assertEqual(bands[2][1:3], ("VNIR", 3))
        self.assertEqual(bands[7][1:3], ("TIR", 5))

    def test_aster_nasa_file_per_band(self):
        s = scene("aster_nasa", {"b1": "1.tif", "b2": "2.tif",
                                 "b3n": "3.tif"})
        self.assertEqual(s2.whole_files(s), ["b1", "b2", "b3n"])
        self.assertEqual([b[1:3] for b in s2.whole_bands(s)],
                         [("b1", 1), ("b2", 1), ("b3n", 1)])

    def test_modis_tiles_without_hdf(self):
        s = scene("modis_lst1", {
            "LST_Day_1km": ("a/day.tif", "b/day.tif"),
            "LST_Night_1km": ("a/night.tif?sig", "b/night.tif"),
            "hdf": "a/file.hdf"})
        self.assertEqual(s2.whole_files(s),
                         ["LST_Day_1km", "LST_Night_1km"])
        self.assertEqual([b[0] for b in s2.whole_bands(s)],
                         ["LST_Day_1km", "LST_Night_1km"])


MSS = ("https://landsateuwest.blob.core.windows.net/landsat-c2/level-1/"
       "standard/mss/1973/181/019/LM01_L1TP_181019_19730606_20200909_02_T2/"
       "LM01_L1TP_181019_19730606_20200909_02_T2_")


def mss_item():
    """Сцена Landsat 1 MSS у Перми 6 июня 1973 года, как в каталоге
    Planetary Computer 12 октября 2026 года."""
    bands = {"green": ("B4", 0.95591, -18.55591),
             "red": ("B5", 0.64843, -0.74843),
             "nir08": ("B6", 0.65236, -0.75236),
             "nir09": ("B7", 0.60866, -0.60866)}
    assets = {k: {"href": MSS + b + ".TIF", "raster:bands": [
        {"scale": scale, "offset": offset, "nodata": 0}]}
        for k, (b, scale, offset) in bands.items()}
    assets["qa_pixel"] = {"href": MSS + "QA_PIXEL.TIF",
                          "raster:bands": [{"nodata": 1}]}
    assets["mtl.json"] = {"href": MSS + "MTL.json"}
    return {"id": "LM01_L1TP_181019_19730606_02_T2",
            "collection": "landsat-c2-l1",
            "properties": {"datetime": "1973-06-06T07:00:36.5Z",
                           "platform": "landsat-1", "proj:epsg": 32640,
                           "eo:cloud_cover": 8.0,
                           "view:sun_elevation": 51.38128591,
                           "landsat:wrs_path": "181",
                           "landsat:wrs_row": "019"},
            "assets": assets}


# Выдержка из mtl.json той же сцены.
MSS_MTL = {"LANDSAT_METADATA_FILE": {
    "LEVEL1_RADIOMETRIC_RESCALING": {
        "REFLECTANCE_MULT_BAND_4": "1.7269E-03",
        "REFLECTANCE_MULT_BAND_5": "1.3650E-03",
        "REFLECTANCE_MULT_BAND_6": "1.6568E-03",
        "REFLECTANCE_MULT_BAND_7": "2.3270E-03",
        "REFLECTANCE_ADD_BAND_4": "-0.033522",
        "REFLECTANCE_ADD_BAND_5": "-0.001575",
        "REFLECTANCE_ADD_BAND_6": "-0.001911",
        "REFLECTANCE_ADD_BAND_7": "-0.002327"},
    "IMAGE_ATTRIBUTES": {"SUN_ELEVATION": "51.38128591"}}}


class TestMss(unittest.TestCase):
    def test_item_is_mss(self):
        s = s2.parse_item(mss_item())
        self.assertEqual(s.mission, "mss")
        self.assertEqual(s.tile, "L1 181/019")
        self.assertEqual(s2.file_name(s, "ndvi"),
                         "LM1_19730606_181-019_ndvi")
        self.assertEqual(s2.credit(s), "Landsat 1 image courtesy of the "
                                       "U.S. Geological Survey")
        self.assertTrue(s2.needs_key("mss"))

    def test_search_and_steps(self):
        body = s2.search_body({"type": "Point", "coordinates": [56, 58]},
                              "1975-05-01", "1975-09-30", 50, mission="mss")
        self.assertEqual(body["collections"], ["landsat-c2-l1"])
        self.assertEqual(s2.step_for([(0, 0), (3000, 3000)], "mss"), 60.0)
        self.assertEqual(s2.CLOUD_ASSET["mss"], ("qa_pixel", 60.0))

    def test_toa_reflectance(self):
        # Значение 100 красного канала: (1.365e-3 × 100 - 0.001575)
        # / sin(51.38°) = 0.1727. Каталог давал бы яркость 64.1.
        s = s2.toa(s2.parse_item(mss_item()), MSS_MTL)
        value = s2.reflectance(np.array([[0, 100]], np.uint8),
                               s.assets["red"])
        self.assertTrue(np.isnan(value[0, 0]))
        expected = (1.365e-3 * 100 - 0.001575) / math.sin(
            math.radians(51.38128591))
        self.assertAlmostEqual(float(value[0, 1]), expected, 5)
        # mtl.json не масштабируется, у зелёного - свой канал B4.
        self.assertEqual(s.assets["mtl.json"].scale, 1.0)
        self.assertAlmostEqual(s.assets["green"].offset * math.sin(
            math.radians(51.38128591)), -0.033522, 6)

    def test_products(self):
        self.assertEqual(s2.products_of("mss"),
                         ("infrared", "mss_bands", "ndvi", "ndwi"))
        self.assertEqual(s2.needed(["infrared", "mss_bands"], "mss"),
                         ["nir08", "red", "green", "nir09"])
        one = np.full((1, 1), 0.1, np.float32)
        bands = {"green": one, "red": one * 2, "nir08": one * 3,
                 "nir09": one * 4}
        stack = s2.product("mss_bands", bands, "mss")
        self.assertEqual(stack.shape, (4, 1, 1))
        self.assertAlmostEqual(float(stack[3, 0, 0]), 0.4, 6)
        self.assertAlmostEqual(float(s2.product("ndvi", bands,
                                                "mss")[0, 0]), 0.2, 5)

    def test_saturated_line_is_filled(self):
        # Строка насыщенного зелёного (бит 3 у B4 Landsat 1-3) среди
        # ровного поля 0.1 заменяется соседями, сплошная насыщенная
        # область без целых соседей остаётся.
        s = s2.parse_item(mss_item())
        bit = s2.radsat_bit(s.assets["green"])
        self.assertEqual(bit, 3)
        self.assertEqual(s2.radsat_bit(s.assets["nir09"]), 6)
        # Полоса - строки 3-4 насыщены, строки 2 и 5 провалены в тёмное,
        # как на сцене 21 сентября 1975 года.
        values = np.full((8, 5), 0.1, np.float32)
        values[3:5, :] = 0.9
        values[2, :] = values[5, :] = 0.03
        radsat = np.zeros((8, 5), np.uint16)
        radsat[3:5, :] = 1 << bit
        filled, count = s2.fill_saturated(values, radsat, bit)
        self.assertEqual(count, 20)
        self.assertTrue(np.allclose(filled, 0.1))
        # Насыщение другого канала зелёный не трогает.
        same, none = s2.fill_saturated(values, radsat << 1, bit)
        self.assertEqual(none, 0)
        self.assertAlmostEqual(float(same[3, 2]), 0.9, 6)
        # Облако выше STRIPE_ROWS строк остаётся целиком.
        cloud = np.full((9, 5), 0.1, np.float32)
        cloud[1:8, :] = 0.9
        flags = np.zeros((9, 5), np.uint16)
        flags[1:8, :] = 1 << bit
        kept, none = s2.fill_saturated(cloud, flags, bit)
        self.assertEqual(none, 0)
        self.assertTrue(np.allclose(kept[1:8], 0.9))

    def test_clean_mss_zone(self):
        # Насыщенный пиксель зелёного, рядом в зоне полосы - провал
        # зелёного без отметки, далеко от полосы - такой же провал,
        # он настоящий и остаётся.
        bands = {k: np.full((12, 20), 0.1, np.float32)
                 for k in s2.MSS_BANDS}
        bands["green"][5, 5] = 0.9
        bands["green"][6, 8] = 0.03
        bands["green"][10, 17] = 0.03
        radsat = np.zeros((12, 20), np.uint16)
        radsat[5, 5] = 1 << 3
        bits = {"green": 3, "red": 4, "nir08": 5, "nir09": 6}
        out, done = s2.clean_mss(bands, radsat, bits)
        self.assertAlmostEqual(float(out["green"][5, 5]), 0.1, 6)
        self.assertAlmostEqual(float(out["green"][6, 8]), 0.1, 6)
        self.assertAlmostEqual(float(out["green"][10, 17]), 0.03, 6)
        self.assertTrue(np.allclose(out["red"], 0.1))
        self.assertGreaterEqual(done, 2)

    def test_single_band_spike_is_found(self):
        # Всплеск зелёного на ровном поле - полоса, яркая крыша во всех
        # каналах - нет.
        flat = np.full((5, 5), 0.1, np.float32)
        bands = {k: flat.copy() for k in s2.MSS_BANDS}
        bands["green"][2, 1] = 0.4
        for key in s2.MSS_BANDS:
            bands[key][2, 3] = 0.4
        found = s2.spikes(bands)
        self.assertEqual(np.argwhere(found["green"]).tolist(), [[2, 1]])
        self.assertFalse(found["red"].any())
        fixed, count = s2.fill_mask(bands["green"], found["green"])
        self.assertEqual(count, 1)
        self.assertAlmostEqual(float(fixed[2, 1]), 0.1, 6)
        self.assertAlmostEqual(float(fixed[2, 3]), 0.4, 6)

    def test_qa_cloud_bit(self):
        # Бит 3 - облако, бит 0 - нет данных, как у qa_pixel MSS.
        qa = np.array([[0, 8], [1, 0]], dtype=np.uint16)
        cloud, valid = s2.clouds_of(s2.parse_item(mss_item()), qa,
                                    np.ones((2, 2), dtype=bool))
        self.assertAlmostEqual(cloud, 100.0 / 3.0)
        self.assertAlmostEqual(valid, 75.0)


if __name__ == "__main__":
    unittest.main()
