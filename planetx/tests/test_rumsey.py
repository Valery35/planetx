# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Карты Рамсея: указатель, карты у вида, куски IIIF, привязка."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import rumsey  # noqa: E402

INDEX = {"maps": [
    [0, 37.0, 55.5, 38.0, 56.0, 1739, "Moskva plan", 8400, "50_30"],
    [1, 20.0, 40.0, 60.0, 70.0, 1745, "Russia", 5000000, "50_40"],
    [2, -180.0, -90.0, 180.0, 90.0, 1800, "World", None, "0_0"],
    [3, 2.0, 48.0, 3.0, 49.0, 1700, "Paris", 10000, "40_0"],
    [4, 37.5, 55.6, 37.8, 55.9, 1935, "Moskva centre", 2000, "50_30"]]}


class TestRumsey(unittest.TestCase):

    def test_covering_order(self):
        cat = rumsey.Catalogue.from_text(json.dumps(INDEX))
        rows = rumsey.covering(cat, 55.75, 37.62, (37.3, 55.5, 37.9, 56.0))
        numbers = [int(cat.number[r]) for r in rows]
        # Подробные сначала, карта мира - в конце, Париж не задет.
        self.assertEqual(numbers, [4, 0, 1, 2])

    def test_tile_plan(self):
        factor, w, h, pieces = rumsey.tile_plan(7984, 6160,
                                                [1, 2, 4, 8, 16, 32])
        self.assertEqual(factor, 4)
        self.assertEqual((w, h), (1996, 1540))
        self.assertEqual(len(pieces), 8 * 7)
        last = pieces[-1]
        self.assertEqual(last[:4], (7168, 6144, 816, 16))
        self.assertEqual(last[4:], (1792, 1536, 204, 4))
        url = rumsey.piece_url("https://x/iiif/abc", pieces[0])
        self.assertEqual(url, "https://x/iiif/abc/0,0,1024,1024/256,/0/"
                         "default.jpg")

    def test_small_image_full_size(self):
        factor, w, h, pieces = rumsey.tile_plan(1000, 800, [1, 2, 4])
        self.assertEqual((factor, w, h, len(pieces)), (1, 1000, 800, 16))

    def test_warp_options(self):
        self.assertEqual(rumsey.warp_options("tps", 12), {"tps": True})
        self.assertEqual(rumsey.warp_options("polynomial", 6),
                         {"polynomialOrder": 2})
        self.assertEqual(rumsey.warp_options("affine", 4),
                         {"polynomialOrder": 1})

    def test_image_url(self):
        self.assertEqual(rumsey.image_url("abc"),
                         "https://images.iiifhosting.com/iiif/abc")
        self.assertEqual(rumsey.image_url("https://y/z"), "https://y/z")


if __name__ == "__main__":
    unittest.main()
