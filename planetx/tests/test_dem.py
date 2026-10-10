# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Рельеф на выбор: имена файлов Copernicus, рамки тайлов, слияние."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import dem  # noqa: E402


class TestDem(unittest.TestCase):
    def test_copernicus_names(self):
        self.assertEqual(dem.copernicus_name(58, 56),
                         "Copernicus_DSM_COG_10_N58_00_E056_00_DEM")
        self.assertEqual(dem.copernicus_name(-34, -71),
                         "Copernicus_DSM_COG_10_S34_00_W071_00_DEM")
        self.assertIn("/Copernicus_DSM_COG_10_N58_00_E056_00_DEM/",
                      dem.copernicus_url(58, 56))

    def test_cells_of_tile(self):
        # Тайл уровня 9 у Перми задевает градусы 57-58 и 56.
        west, south, east, north = dem.tile_degrees(9, 336, 150)
        cells = dem.copernicus_cells(west, south, east, north)
        self.assertTrue(cells)
        for lat, lon in cells:
            self.assertTrue(south - 1 < lat <= north)
            self.assertTrue(west - 1 < lon <= east)
        self.assertEqual(dem.copernicus_cells(179.5, 10.2, 180.5, 10.4),
                         [(10, 179), (10, -180)])

    def test_tile_bounds_agree(self):
        west, south, east, north = dem.tile_meters(0, 0, 0)
        self.assertAlmostEqual(west, -20037508.34, places=1)
        self.assertAlmostEqual(north, 20037508.34, places=1)
        degrees = dem.tile_degrees(0, 0, 0)
        self.assertAlmostEqual(degrees[3], 85.0511, places=3)

    def test_merge_keeps_sea_floor(self):
        base = np.array([[-3000.0, 120.0], [5.0, -2.0]], dtype=np.float32)
        model = np.array([[0.0, 131.0], [np.nan, 4.0]], dtype=np.float32)
        out = dem.merge(base, model)
        self.assertEqual(out[0, 0], -3000.0)  # море - от Terrarium
        self.assertEqual(out[0, 1], 131.0)  # суша - модель
        self.assertEqual(out[1, 0], 5.0)  # нет данных модели
        self.assertEqual(out[1, 1], 4.0)  # берег выше нуля - модель
        self.assertIs(dem.merge(base, None), base)

    def test_choice(self):
        self.assertEqual(dem.choice("gedtm30"), dem.GEDTM)
        self.assertEqual(dem.choice(""), dem.TERRARIUM)
        self.assertEqual(dem.choice(None), dem.TERRARIUM)


if __name__ == "__main__":
    unittest.main()
