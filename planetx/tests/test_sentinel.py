# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки Sentinel-2: тайл точки, файлы года, разбор строк каталога."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import sentinel as s2  # noqa: E402


def row(id_, when, cloud, visual=True):
    assets = {"thumbnail": {"href": "https://x/PVI.jpg"}}
    if visual:
        assets["visual"] = {"href": "https://x/TCI.tif"}
    return {"id": id_, "datetime": when, "eo:cloud_cover": cloud,
            "thumbnail_url": None, "assets": json.dumps(assets)}


class TestSentinel(unittest.TestCase):

    def test_tile_of_point(self):
        # Тайл у Перми по каталогу 9 октября 2026 года - 40VDK, у Нью-
        # Йорка зона одной цифрой дополняется нулём: 18TWL.
        self.assertEqual(s2.tile_of(58.0105, 56.2294), "40VDK")
        self.assertEqual(s2.tile_of(40.7128, -74.0060), "18TWL")
        self.assertEqual(s2.tile_of(-33.87, 151.21)[:2], "56")
        self.assertIsNone(s2.tile_of(85.0, 10.0))

    def test_year_files(self):
        old = s2.year_files(2025, 2026, 10)
        self.assertEqual(old, [s2.CATALOG + "year=2025/items.parquet"])
        now = s2.year_files(2026, 2026, 3)
        self.assertEqual(len(now), 4)
        self.assertTrue(now[-1].endswith("year=2026/live-03.parquet"))

    def test_filter_is_safe(self):
        self.assertEqual(s2.tile_filter("40VDK"), "\"_tile\" = '40VDK'")
        with self.assertRaises(ValueError):
            s2.tile_filter("40VDK' OR 1=1 --")

    def test_scenes_sorted_filtered_unique(self):
        scenes = [s2.scene(r, "40VDK") for r in (
            row("a", "2025/07/14 07:43:28.9+00", 3.0),
            row("b", "2025/08/01 07:33:30+00", 80.0),
            row("c", "2025/09/02 07:53:24+00", 10.0),
            row("c", "2025/09/02 07:53:24+00", 10.0))]
        self.assertEqual(scenes[0].when, "2025-07-14 07:43")
        self.assertEqual(scenes[0].thumbnail, "https://x/PVI.jpg")
        chosen = s2.choose(scenes, 30)
        self.assertEqual([x.id for x in chosen], ["c", "a"])
        self.assertIsNone(s2.scene(row("d", "2025/01/01", 1, False), "x"))
        self.assertEqual(s2.layer_name(chosen[1]),
                         "Sentinel-2 40VDK 2025-07-14, 3 %")


if __name__ == "__main__":
    unittest.main()
