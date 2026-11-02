# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Минеральные карты EMIT: каталог, сетка GLT, классы минералов."""
import os
import sys
import unittest
from urllib.parse import parse_qs, urlsplit

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import emit  # noqa: E402


def _item(ur, start, version, cloud=10):
    base = ("https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/"
            "EMITL2BMIN.{v}/{ur}/".format(v=version, ur=ur))
    public = base.replace("protected", "public")
    return {"umm": {
        "GranuleUR": ur,
        "TemporalExtent": {"RangeDateTime": {
            "BeginningDateTime": start, "EndingDateTime": start}},
        "CloudCover": cloud,
        "SpatialExtent": {"HorizontalSpatialDomain": {"Geometry": {
            "GPolygons": [{"Boundary": {"Points": [
                {"Longitude": -116.0, "Latitude": 37.0},
                {"Longitude": -117.5, "Latitude": 37.0},
                {"Longitude": -117.5, "Latitude": 38.0},
                {"Longitude": -116.0, "Latitude": 38.0},
                {"Longitude": -116.0, "Latitude": 37.0}]}}]}}},
        "RelatedUrls": [
            {"URL": "https://opendap.earthdata.nasa.gov/x/" + ur,
             "Type": "USE SERVICE API"},
            {"URL": base + ur + ".nc", "Type": "GET DATA"},
            {"URL": base + ur.replace("_MIN_", "_MINUNCERT_") + ".nc",
             "Type": "GET DATA"},
            {"URL": public + ur + ".png",
             "Type": "GET RELATED VISUALIZATION"},
            {"URL": "s3://lp-prod-protected/x/" + ur + ".nc",
             "Type": "GET DATA VIA DIRECT ACCESS"}]}}


class TestCatalog(unittest.TestCase):
    def test_url(self):
        ring = [(37.4, -117.3), (37.4, -117.1), (37.6, -117.2)]
        query = parse_qs(urlsplit(emit.cmr_url(
            ring, "2023-01-01", "2024-12-31", 30,
            emit.COLLECTIONS[0][0])).query)
        self.assertEqual(query["collection_concept_id"],
                         ["C4079846859-LPCLOUD"])
        self.assertEqual(query["bounding_box"],
                         ["-117.300000,37.400000,-117.100000,37.600000"])
        self.assertEqual(query["cloud_cover"], ["0,30"])

    def test_parse_takes_min_file_not_uncertainty(self):
        scenes = emit.parse_cmr({"items": [_item(
            "EMIT_L2B_MIN_002_20261005T164917",
            "2026-10-05T16:49:17Z", "002")]}, "002")
        self.assertEqual(len(scenes), 1)
        s = scenes[0]
        self.assertTrue(s["url"].endswith(
            "/EMIT_L2B_MIN_002_20261005T164917.nc"))
        self.assertTrue(s["preview"].endswith(".png"))
        self.assertEqual(s["when"], "2026-10-05 16:49:17")
        self.assertEqual(len(s["polygon"]), 4)
        self.assertEqual(s["version"], "002")

    def test_merge_prefers_first_version(self):
        new = emit.parse_cmr({"items": [_item(
            "EMIT_L2B_MIN_002_20230801T100000",
            "2023-08-01T10:00:00Z", "002")]}, "002")
        old = emit.parse_cmr({"items": [
            _item("EMIT_L2B_MIN_001_20230801T100000_2321308_005",
                  "2023-08-01T10:00:00Z", "001"),
            _item("EMIT_L2B_MIN_001_20240901T100000_2424508_006",
                  "2024-09-01T10:00:00Z", "001")]}, "001")
        merged = emit.merge([new, old])
        self.assertEqual([s["version"] for s in merged], ["001", "002"])
        self.assertEqual(merged[1]["when"], "2023-08-01 10:00:00")

    def test_coverage(self):
        polygon = [(37.0, -116.0), (37.0, -117.5), (38.0, -117.5),
                   (38.0, -116.0)]
        inner = [(37.4, -117.3), (37.4, -117.1), (37.6, -117.1),
                 (37.6, -117.3)]
        self.assertAlmostEqual(emit.coverage(polygon, inner), 1.0)
        half = [(37.9, -117.0), (37.9, -116.5), (38.1, -116.5),
                (38.1, -117.0)]
        self.assertGreater(emit.coverage(polygon, half), 0.3)
        self.assertLess(emit.coverage(polygon, half), 0.7)
        away = [(10.0, 10.0), (10.0, 11.0), (11.0, 11.0), (11.0, 10.0)]
        self.assertEqual(emit.coverage(polygon, away), 0.0)


class TestGrid(unittest.TestCase):
    def test_ortho_takes_one_based_rows_and_columns(self):
        swath = np.arange(12, dtype=np.float32).reshape(3, 4)
        glt_x = np.array([[1, 4, 0], [2, 3, 4]])
        glt_y = np.array([[1, 3, 0], [2, -2, 1]])
        out = emit.ortho(swath, glt_x, glt_y)
        self.assertEqual(out[0, 0], 0.0)
        self.assertEqual(out[0, 1], 11.0)
        self.assertTrue(np.isnan(out[0, 2]))
        self.assertEqual(out[1, 0], 5.0)
        self.assertEqual(out[1, 1], 6.0)  # знак таблицы не учитывается
        self.assertEqual(out[1, 2], 3.0)

    def test_ortho_of_ids_keeps_integers(self):
        ids = np.array([[5, 7]], dtype=np.int16)
        out = emit.ortho(ids, np.array([[2, 0]]), np.array([[1, 0]]),
                         fill=-1)
        self.assertEqual(out.tolist(), [[7, -1]])

    def test_fit_transform(self):
        rows, cols = 4, 5
        lats = 40.0 - 0.01 * (np.arange(rows)[:, None] + 0.5) \
            + 0 * np.arange(cols)[None, :]
        lons = 10.0 + 0.02 * (np.arange(cols)[None, :] + 0.5) \
            + 0 * np.arange(rows)[:, None]
        glt_y, glt_x = np.mgrid[1:rows + 1, 1:cols + 1]
        gt = emit.fit_transform(glt_x, glt_y, lats, lons)
        self.assertTrue(emit.fit_ok(gt))
        self.assertAlmostEqual(gt[0], 10.0, places=9)
        self.assertAlmostEqual(gt[1], 0.02, places=9)
        self.assertAlmostEqual(gt[3], 40.0, places=9)
        self.assertAlmostEqual(gt[5], -0.01, places=9)


class TestClasses(unittest.TestCase):
    def test_classes_by_area_without_empty_cells(self):
        ids = np.array([[3, 3, 3], [9, 9, -9999], [3, 0, 7]])
        depth = np.array([[0.1, 0.2, 0.1], [0.1, 0.3, 0.2],
                          [np.nan, 0.0, 0.05]])
        kinds, kept = emit.classes(ids, depth)
        self.assertEqual(kept, [3, 9, 7])
        self.assertEqual(kinds.tolist(), [[0, 0, 0], [1, 1, -1],
                                          [-1, -1, 2]])
        shares = emit.shares(kinds, len(kept))
        self.assertEqual(shares[0], (0, 3 / 6))

    def test_mask(self):
        ids = np.array([[1, 2]])
        depth = np.array([[0.1, 0.1]])
        kinds, kept = emit.classes(ids, depth, np.array([[False, True]]))
        self.assertEqual(kept, [2])
        self.assertEqual(kinds.tolist(), [[-1, 0]])

    def test_many_minerals_keep_rest_class(self):
        ids = np.arange(300).reshape(1, 300)
        depth = np.ones(ids.shape)
        kinds, kept = emit.classes(ids, depth)
        self.assertEqual(len(kept), emit.MOST)
        self.assertEqual(kept[-1], -1)
        self.assertEqual(int(kinds.max()), emit.MOST - 1)
        self.assertEqual(emit.color(-1), (160, 160, 160))

    def test_names_prefer_sample_name(self):
        names = emit.names_of(
            [0, 1, 0], [1, 1, 2],
            ["lib/s07_Goethite_WS222.txt", "Hematite_GDS27", "kao.txt"],
            ["", "Hematite GDS27", "Kaolinite CM9"])
        self.assertEqual(names[1][0], "s07_Goethite_WS222")
        self.assertEqual(names[1][1], "Hematite GDS27")
        self.assertEqual(names[2][0], "Kaolinite CM9")


if __name__ == "__main__":
    unittest.main()
