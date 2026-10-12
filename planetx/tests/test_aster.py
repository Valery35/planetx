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

    def test_search_body(self):
        body = s2.search_body({"type": "Point", "coordinates": [-117, 37]},
                              "2000-03-04", "2006-12-31", 50,
                              mission="aster")
        self.assertEqual(body["collections"], ["aster-l1t"])


if __name__ == "__main__":
    unittest.main()
