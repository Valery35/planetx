# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""MODIS в окне снимков: разбор каталога, значения, качество, тайлы."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import modis  # noqa: E402
import sentinel as s2  # noqa: E402


def _item(number, day, h=20, v=3, keys=("LST_Day_1km", "LST_Night_1km")):
    assets = {k: {"href": "https://modis/{}/{}.tif".format(number, k),
                  "type": "image/tiff; application=geotiff"} for k in keys}
    assets["hdf"] = {"href": "https://modis/x.hdf",
                     "type": "application/x-hdf"}
    return {"id": number, "collection": "modis-11A1-061",
            "properties": {"start_datetime": day + "T00:00:00Z",
                           "modis:horizontal-tile": h,
                           "modis:vertical-tile": v},
            "assets": assets}


class TestCatalogue(unittest.TestCase):
    def test_item_and_body(self):
        s = s2.parse_item(_item("MYD11A1.A2024213.h20v03.061.1", "2024-07-31"))
        self.assertEqual(s.mission, "modis_lst1")
        self.assertEqual(s.when, "2024-07-31")
        self.assertEqual(s.tile, "Aqua h20v03")
        self.assertNotIn("hdf", s.assets)
        self.assertEqual(s.assets["LST_Day_1km"].href,
                         ("https://modis/MYD11A1.A2024213.h20v03.061.1/"
                          "LST_Day_1km.tif",))
        body = s2.search_body({}, "2024-01-01", "2024-12-31", 50,
                              mission="modis_lst1")
        self.assertNotIn("query", body)
        self.assertEqual(body["collections"], ["modis-11A1-061"])
        self.assertTrue(s2.needs_key("modis_veg"))
        self.assertTrue(s2.sas_url("modis_veg").endswith("modis-13Q1-061"))
        self.assertEqual(s2.sign(("a", "b?x=1"), "k=2"),
                         ("a?k=2", "b?x=1&k=2"))

    def test_tiles_of_one_day_merge(self):
        scenes = [s2.parse_item(_item("MOD11A1.A1.h20v03", "2024-07-30")),
                  s2.parse_item(_item("MOD11A1.A1.h21v03", "2024-07-30", 21)),
                  s2.parse_item(_item("MYD11A1.A1.h20v03", "2024-07-30")),
                  s2.parse_item(_item("MOD11A1.A2.h20v03", "2024-07-31"))]
        merged = modis.merge_tiles(scenes)
        self.assertEqual([s.when for s in merged],
                         ["2024-07-31", "2024-07-30", "2024-07-30"])
        terra = next(s for s in merged if s.tile.startswith("Terra h20v03,"))
        self.assertEqual(len(terra.assets["LST_Day_1km"].href), 2)

    def test_utm_of_area(self):
        ring = s2.square(58.01, 56.23, 3000.0)
        self.assertEqual(modis.utm_epsg(ring), 32640)
        self.assertEqual(modis.utm_epsg([(-33.9, 18.4)]), 32734)


class TestValues(unittest.TestCase):
    def test_temperature_and_vegetation(self):
        lst = modis.value("lst_day", np.array([[0, 14657]], dtype=np.uint16))
        self.assertTrue(np.isnan(lst[0, 0]))
        self.assertAlmostEqual(float(lst[0, 1]), 19.99, places=2)
        ndvi = modis.value("modis_ndvi",
                           np.array([[-3000, 8000]], dtype=np.int16))
        self.assertTrue(np.isnan(ndvi[0, 0]))
        self.assertAlmostEqual(float(ndvi[0, 1]), 0.8, places=4)

    def test_snow_and_burn(self):
        cover = modis.value("snow_cover",
                            np.array([[0, 64, 250]], dtype=np.uint8))
        self.assertEqual(cover[0, 1], 64.0)
        self.assertTrue(np.isnan(cover[0, 2]))
        extent = modis.value("snow_extent",
                             np.array([[25, 200, 100, 50]], dtype=np.uint8))
        self.assertEqual(list(extent[0, :3]), [0.0, 1.0, 2.0])
        self.assertTrue(np.isnan(extent[0, 3]))
        burn = modis.value("burn_date", np.array([[0, 200, -1]],
                                                 dtype=np.int16))
        self.assertEqual(burn[0, 1], 200.0)
        self.assertTrue(np.isnan(burn[0, 0]) and np.isnan(burn[0, 2]))

    def test_quality_over_area(self):
        inside = np.array([[True, True, True, False]])
        cloud, valid = modis.quality(
            "modis_snow1", np.array([[250, 30, 255, 250]]), inside)
        self.assertAlmostEqual(cloud, 50.0)
        self.assertAlmostEqual(valid, 200.0 / 3.0)
        cloud, valid = modis.quality(
            "modis_lst8", np.array([[0, 14000, 14000, 0]]), inside)
        self.assertAlmostEqual(cloud, 100.0 / 3.0)

    def test_colorize_and_names(self):
        rgb = modis.colorize(np.array([[np.nan, 45.0]], dtype=np.float32),
                             modis.TEMPERATURE)
        self.assertEqual(rgb.shape, (3, 1, 2))
        self.assertEqual(list(rgb[:, 0, 1]), [165, 0, 38])
        self.assertEqual(list(rgb[:, 0, 0]), [90, 90, 90])
        s = s2.parse_item(_item("MOD11A1.A2024213.h20v03.061.1",
                                "2024-07-31"))
        self.assertEqual(s2.file_name(s, "lst_day"),
                         "MODIS_Terra_20240731_lst_day")
        self.assertEqual(s2.credit(s), "MOD11A1 v061, NASA EOSDIS LP DAAC")
        self.assertIn("NSIDC", modis.credit("MYD10A1.A1"))


if __name__ == "__main__":
    unittest.main()
