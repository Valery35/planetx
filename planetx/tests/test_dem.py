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


class TestModels(unittest.TestCase):
    # ALOS AW3D30, NASADEM и USGS 3DEP на Planetary Computer, адреса
    # сверены по каталогу STAC 25 октября 2026 года.
    def test_cell_names(self):
        self.assertEqual(dem.cell_name(dem.ALOS, 58, 56), "N058E056")
        self.assertEqual(dem.cell_name(dem.ALOS, -34, -71), "S034W071")
        self.assertEqual(dem.cell_name(dem.NASADEM, 57, 56), "n57e056")
        # 3DEP - по северо-западному углу: градус 39-40, -106..-105.
        self.assertEqual(dem.cell_name(dem.USGS, 39, -106), "n40w106")

    def test_file_urls(self):
        urls = dem.file_urls(dem.USGS, -105.5, 39.2, -105.2, 39.8)
        self.assertEqual(urls, ["https://ai4edataeuwest.blob.core.windows.net/"
                                "3dep/Elevation/13/TIFF/n40w106/"
                                "USGS_13_n40w106.tif"])
        self.assertEqual(len(dem.file_urls(dem.NASADEM, 56.5, 57.5, 57.5,
                                           58.5)), 4)
        self.assertEqual(dem.file_urls(dem.GEDTM, 0, 0, 1, 1),
                         [dem.GEDTM_URL])

    def test_new_choices_need_key(self):
        for kind in (dem.ALOS, dem.NASADEM, dem.USGS):
            self.assertEqual(dem.choice(kind), kind)
            self.assertIn(kind, dem.SAS)
            self.assertIn(kind, dem.ATTRIBUTION)
        self.assertNotIn(dem.COPERNICUS, dem.SAS)
        self.assertEqual(dem.signed("https://a/b.tif", "sv=1&sig=x"),
                         "https://a/b.tif?sv=1&sig=x")
        self.assertEqual(dem.signed("https://a/b.tif", ""), "https://a/b.tif")


class TestSea(unittest.TestCase):
    def test_merge_sea_keeps_land(self):
        base = np.array([[-3000.0, 0.0], [120.0, -5.0], [0.0, 2.0]],
                        dtype=np.float32)
        sea = np.array([[-3400.0, -7100.0], [-20.0, np.nan], [15.0, -1.0]],
                       dtype=np.float32)
        out = dem.merge_sea(base, sea)
        self.assertEqual(out[0, 0], -3400.0)  # дно - GEBCO
        self.assertEqual(out[0, 1], -7100.0)  # пустой ноль Terrarium
        self.assertEqual(out[1, 0], 120.0)  # суша тайла остаётся
        self.assertEqual(out[1, 1], -5.0)  # нет данных GEBCO
        self.assertEqual(out[2, 0], 0.0)  # суша GEBCO берег не двигает
        self.assertEqual(out[2, 1], 2.0)
        self.assertIs(dem.merge_sea(base, None), base)

    def test_sea_choice_and_levels(self):
        self.assertEqual(dem.sea_choice(""), dem.SEA_DEFAULT)
        self.assertEqual(dem.sea_choice(dem.TERRARIUM), dem.TERRARIUM)
        self.assertEqual(dem.sea_choice("x"), dem.SEA_DEFAULT)
        self.assertEqual(dem.levels(dem.GEBCO),
                         (dem.SEA_MIN_LEVEL, dem.SEA_READ_LEVEL))
        self.assertEqual(dem.levels(dem.COPERNICUS),
                         (dem.MIN_LEVEL, dem.READ_LEVEL))
        self.assertIn(dem.GEBCO, dem.ATTRIBUTION)

    def test_has_sea(self):
        self.assertFalse(dem.has_sea(np.full((4, 4), 12.0)))
        self.assertTrue(dem.has_sea(np.array([[12.0, 0.0]])))


if __name__ == "__main__":
    unittest.main()
