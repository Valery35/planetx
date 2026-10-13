# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки ASTER: перевод значений, продукты, сцена каталога."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import aster  # noqa: E402
import sentinel as s2  # noqa: E402

BASE = ("https://astersa.blob.core.windows.net/aster/images/L1T/2006/08/"
        "15/AST_L1T_00308152006183834_20150515181406_80216")


def item(swir=True):
    """Сцена ASTER у Куприта 15 августа 2006 года, как в каталоге
    Planetary Computer 12 октября 2026 года."""
    assets = {"VNIR": {"href": BASE + ".VNIR.tif"},
              "TIR": {"href": BASE + ".TIR.tif"},
              "xml": {"href": BASE + ".hdf.xml"},
              "rendered_preview": {
                  "href": "https://planetarycomputer.microsoft.com/api/"
                          "data/v1/item/preview.png?collection=aster-l1t"}}
    if swir:
        assets["SWIR"] = {"href": BASE + ".SWIR.tif"}
    return {"id": "AST_L1T_00308152006183834_20150515181406",
            "collection": "aster-l1t",
            "properties": {"datetime": "2006-08-15T18:38:34.177Z",
                           "platform": "terra", "proj:epsg": 32611,
                           "eo:cloud_cover": 0.0,
                           "view:sun_elevation": 62.5},
            "assets": assets}


class TestValues(unittest.TestCase):
    def test_radiance_and_nodata(self):
        lum = aster.radiance(np.array([[0, 101]], np.uint8), "b1")
        self.assertTrue(np.isnan(lum[0, 0]))
        self.assertAlmostEqual(float(lum[0, 1]), 100 * 1.688, 3)

    def test_reflectance(self):
        # Отражение = π L d² / (ESUN sin h).
        value = aster.value(np.array([[101]], np.uint8), "b2", 30.0, 4)
        d = aster.sun_distance(4)
        self.assertAlmostEqual(d, 0.98328, 4)
        expected = math.pi * 141.5 * d * d / (1555.74 * 0.5)
        self.assertAlmostEqual(float(value[0, 0]), expected, 4)

    def test_brightness_temperature_inverts(self):
        # Яркость чёрного тела 300 К в канале 13 даёт обратно 300 К.
        k1, k2 = aster.THERMAL["b13"]
        lum = k1 / (math.exp(k2 / 300.0) - 1.0)
        dn = np.array([[round(lum / aster.BANDS["b13"][3] + 1)]], np.uint16)
        kelvin = aster.value(dn, "b13", 60.0, 200)
        self.assertAlmostEqual(float(kelvin[0, 0]), 300.0, 0)


class TestProducts(unittest.TestCase):
    def test_needed_and_files(self):
        self.assertEqual(aster.needed(["aloh", "ferric"]),
                         ["b1", "b2", "b5", "b6", "b7"])
        self.assertEqual(aster.files_of(["b1", "b5", "b13"]),
                         {"VNIR": ["b1"], "SWIR": ["b5"], "TIR": ["b13"]})
        self.assertEqual(len(aster.needed(["all_bands"])), 14)

    def test_without_swir(self):
        s = s2.parse_item(item(swir=False))
        self.assertEqual(aster.available(["aster_false", "aloh", "quartz"],
                                         s.assets),
                         ["aster_false", "quartz"])
        self.assertEqual(s2.all_keys(s), ["b1", "b2", "b3n", "b10", "b11",
                                          "b12", "b13", "b14"])

    def test_ratios(self):
        one = np.full((1, 1), 0.1, np.float32)
        bands = {"b1": one, "b2": one * 2, "b4": one * 3, "b5": one,
                 "b6": one * 2, "b7": one * 3, "b8": one, "b9": one,
                 "L10": one, "L11": one * 2, "L12": one * 4}
        self.assertAlmostEqual(
            float(aster.product("kaolinite", bands)[0, 0]), 5.0, 5)
        self.assertNotIn("ndvi", aster.PRODUCTS)
        self.assertAlmostEqual(float(aster.product("aloh", bands)[0, 0]),
                               2.0, 5)
        self.assertAlmostEqual(float(aster.product("mgoh", bands)[0, 0]),
                               4.0, 5)
        self.assertAlmostEqual(float(aster.product("ferric", bands)[0, 0]),
                               2.0, 5)
        self.assertAlmostEqual(float(aster.product("quartz", bands)[0, 0]),
                               1.0, 5)
        zero = {"b1": np.zeros((1, 1), np.float32), "b2": one}
        self.assertTrue(np.isnan(aster.product("ferric", zero)[0, 0]))


class TestScene(unittest.TestCase):
    def test_item(self):
        s = s2.parse_item(item())
        self.assertEqual(s.mission, "aster")
        self.assertEqual(s.tile, "ASTER")
        self.assertEqual(s.epsg, 32611)
        self.assertEqual(s2.file_name(s, "aloh"), "AST_20060815_aloh")
        self.assertIn("ASTER", s2.credit(s))
        self.assertTrue(s2.needs_key("aster"))
        self.assertEqual(s2.CLOUD_ASSET["aster"], ("VNIR", 90.0))
        self.assertEqual(s2.step_for([(0, 0), (3000, 3000)], "aster"), 15.0)
        self.assertEqual(s2.band_label(s, "b3n"), "B3N 0.82 um")
        self.assertEqual(s2.band_label(s, "b13"), "B13 10.6 um, K")
        self.assertEqual(s2.parse_item(item(swir=False)).tile, "ASTER VNIR")

    def test_area_cloud_is_scene_cloud(self):
        s = s2.parse_item(item())._replace(cloud=12.0)
        raw = np.array([[0, 5], [7, 9]], np.uint8)
        cloud, valid = s2.clouds_of(s, raw, np.ones((2, 2), bool))
        self.assertEqual(cloud, 12.0)
        self.assertAlmostEqual(valid, 75.0)
        self.assertEqual(s2.clear_mask(s, raw).tolist(),
                         [[False, True], [True, True]])

    def test_scene_smaller_than_area_stays_in_list(self):
        # Сцена 60 км на участке 100 км покрывает его на треть, при
        # общем пороге 50 % весь список ASTER был пуст.
        self.assertLess(s2.min_valid("aster"), 30.0)
        self.assertLess(s2.min_valid("aster_nasa"), 30.0)
        self.assertGreater(s2.min_valid("aster"), 0.04)
        self.assertEqual(s2.min_valid("landsat"), 50.0)

    def test_search_body(self):
        body = s2.search_body({"type": "Point", "coordinates": [-117, 37]},
                              "2000-03-04", "2006-12-31", 50,
                              mission="aster")
        self.assertEqual(body["collections"], ["aster-l1t"])


NASA = ("https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/"
        "AST_L1T.004/AST_L1T_00410232024175356_20251007153104/"
        "AST_L1T_00410232024175356_20251007153104_")


def cmr_item(sun=35.99, swir=False):
    """Сцена NASA CMR у Куприта 23 октября 2024 года, как в каталоге
    12 октября 2026 года: только VNIR и TIR."""
    names = ["VNIR_B01", "VNIR_B02", "VNIR_B03N", "TIR_B10", "TIR_B11",
             "TIR_B12", "TIR_B13", "TIR_B14", "VNIR", "TIR"]
    if swir:
        names += ["SWIR_B0{}".format(n) for n in range(4, 10)]
    urls = [{"Type": "GET DATA", "URL": NASA + n + ".tif"} for n in names]
    urls.append({"Type": "GET DATA VIA DIRECT ACCESS",
                 "URL": "s3://lp-prod-protected/x_VNIR_B01.tif"})
    urls.append({"Type": "GET RELATED VISUALIZATION",
                 "URL": NASA.replace("protected", "public")[:-1] + ".jpg"})
    return {"umm": {
        "GranuleUR": "AST_L1T_00410232024175356_20251007153104",
        "TemporalExtent": {"SingleDateTime": "2024-10-23T17:53:56.0Z"},
        "CloudCover": 0,
        "SpatialExtent": {"HorizontalSpatialDomain": {"Geometry": {
            "GPolygons": [{"Boundary": {"Points": [
                {"Longitude": -117.29, "Latitude": 37.58},
                {"Longitude": -116.33, "Latitude": 36.89}]}}]}}},
        "AdditionalAttributes": [
            {"Name": "SolarElevationAngle", "Values": [str(sun)]},
            {"Name": "UTMZone", "Values": ["11"]}],
        "RelatedUrls": urls}}


class TestNasa(unittest.TestCase):
    def test_file_suffix(self):
        self.assertEqual(aster.file_suffix("b3n"), "VNIR_B03N")
        self.assertEqual(aster.file_suffix("b4"), "SWIR_B04")
        self.assertEqual(aster.file_suffix("b14"), "TIR_B14")

    def test_cmr_url(self):
        url = aster.cmr_url([(37.5, -117.3), (37.6, -117.1)], "2018-01-01",
                            "2024-12-31", 20)
        self.assertIn("collection_concept_id=C3306888411-LPCLOUD", url)
        self.assertIn("bounding_box=-117.300000%2C37.500000%2C-117.100000"
                      "%2C37.600000", url)
        self.assertIn("cloud_cover=0%2C20", url)

    def test_parse_day_scene_only(self):
        data = {"items": [cmr_item(), cmr_item(sun=-46.6)]}
        scenes = s2.cmr_scenes(data)
        self.assertEqual(len(scenes), 1)
        s = scenes[0]
        self.assertEqual(s.mission, "aster_nasa")
        self.assertEqual(s.epsg, 32611)
        self.assertEqual(s.when, "2024-10-23 17:53")
        self.assertEqual(s.tile, "ASTER VNIR TIR")
        self.assertEqual(sorted(s.assets), sorted(
            ["b1", "b2", "b3n", "b10", "b11", "b12", "b13", "b14"]))
        self.assertTrue(s.assets["b3n"].href.endswith("_VNIR_B03N.tif"))
        self.assertTrue(s.thumbnail.endswith(".jpg"))
        self.assertFalse(s2.needs_key("aster_nasa"))
        # Без SWIR остаются ложные цвета, железо, кварц, все каналы.
        self.assertEqual(aster.available(aster.PRODUCTS, s.assets),
                         ["aster_false", "ferric", "quartz", "all_bands"])
        self.assertEqual(len(s2.all_keys(s)), 8)
        full = s2.cmr_scenes({"items": [cmr_item(swir=True)]})[0]
        self.assertEqual(full.tile, "ASTER")
        self.assertEqual(len(s2.all_keys(full)), 14)


if __name__ == "__main__":
    unittest.main()
