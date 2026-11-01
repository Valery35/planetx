# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки OpenAerialMap: адрес поиска, разбор ответа, права слоя."""
import os
import sys
import unittest
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "..", "core"))

import oam  # noqa: E402

ROW = {"uuid": "https://oin-hotosm-temp.s3.amazonaws.com/a/0/b.tif",
       "title": " Nanga  Kantor ", "provider": "Drone Pilots",
       "bbox": [120.1, -8.4, 120.2, -8.3], "gsd": 0.04,
       "file_size": 164181646,
       "acquisition_end": "2026-08-29T18:00:00.000Z",
       "properties": {"license": "CC-BY-NC 4.0",
                      "thumbnail": "https://example.org/b.png",
                      "tms": "http://tiles.openaerialmap.org/a/0/b/"
                             "{z}/{x}/{y}"}}


class TestSearch(unittest.TestCase):
    def test_newest_first_in_box(self):
        query = parse_qs(urlparse(oam.search_url((1, 2, 3, 4), 2)).query)
        self.assertEqual(query["bbox"], ["1.00000,2.00000,3.00000,4.00000"])
        self.assertEqual(query["page"], ["2"])
        self.assertEqual(query["order_by"], ["acquisition_end"])
        self.assertEqual(query["sort"], ["desc"])

    def test_box_over_dateline_takes_all_longitudes(self):
        query = parse_qs(urlparse(oam.search_url((179, 2, -179, 4))).query)
        self.assertTrue(query["bbox"][0].startswith("-180.00000,2.00000,"
                                                    "180.00000"))


class TestParse(unittest.TestCase):
    def test_own_license_of_image_is_kept(self):
        images, found = oam.parse({
            "meta": {"license": "CC-BY 4.0", "found": 8}, "results": [ROW]})
        self.assertEqual(found, 8)
        image = images[0]
        self.assertEqual(image.license, "CC BY-NC 4.0")
        self.assertEqual(image.title, "Nanga Kantor")
        self.assertEqual(image.day, "2026-08-29")
        self.assertEqual(image.box, (120.1, -8.4, 120.2, -8.3))

    def test_mistyped_year_gives_no_day(self):
        self.assertEqual(oam.day_of("0206-08-07T00:50:39.000Z"), "")
        self.assertEqual(oam.day_of(None), "")

    def test_row_without_https_file_is_skipped(self):
        row = dict(ROW, uuid="http://example.org/b.tif")
        self.assertEqual(oam.parse({"results": [row, "x"]})[0], [])

    def test_rights_name_provider_and_license(self):
        image = oam.parse({"results": [ROW]})[0][0]
        text = oam.rights(image)
        self.assertIn("Drone Pilots", text)
        self.assertIn("CC BY-NC 4.0", text)
        self.assertIn("Open Imagery Network", text)
        self.assertTrue(oam.is_layer("type=xyz&url=" + image.tiles))

    def test_old_tile_address_goes_over_https(self):
        image = oam.parse({"results": [ROW]})[0][0]
        self.assertTrue(image.tiles.startswith("https://tiles."))

    def test_level_reaches_image_pixel(self):
        image = oam.parse({"results": [ROW]})[0][0]
        self.assertEqual(oam.max_level(image), 22)  # 4 см, предел
        coarse = image._replace(gsd=1.0, box=(0, -1, 1, 1))
        level = oam.max_level(coarse)
        self.assertEqual(level, 18)  # 0.6 м на пиксель уровня 18

    def test_mercator_box_of_equator(self):
        west, south, east, north = oam.mercator_box((-180, 0, 180, 0))
        self.assertAlmostEqual(east - west, oam.CIRCLE)
        self.assertAlmostEqual(south, 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
