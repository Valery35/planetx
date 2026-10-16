# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Ряд снимков участка: продукты, шаг, сводка, деления оси дат, CSV."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import series  # noqa: E402


class TestProducts(unittest.TestCase):

    def test_indices_only(self):
        self.assertEqual(series.products("sentinel2"),
                         ("ndvi", "ndwi", "ndmi", "nbr", "ndsi"))
        self.assertEqual(series.products("landsat")[-1], "lst")
        self.assertEqual(series.products("mss"), ("ndvi", "ndwi"))

    def test_modis_without_classes_and_burn_day(self):
        self.assertEqual(series.products("modis_veg"),
                         ("modis_ndvi", "modis_evi"))
        self.assertEqual(series.products("modis_snow8"), ())
        self.assertEqual(series.products("modis_burn"), ())

    def test_aster_has_no_series(self):
        self.assertEqual(series.products("aster"), ())
        self.assertEqual(series.products("aster_nasa"), ())


class TestStep(unittest.TestCase):

    def test_small_area_keeps_native_step(self):
        xy = [(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 1000.0)]
        self.assertEqual(series.step(xy, "sentinel2"), 10.0)
        self.assertEqual(series.step(xy, "landsat"), 30.0)

    def test_large_area_is_coarse(self):
        xy = [(0.0, 0.0), (50000.0, 0.0), (50000.0, 50000.0),
              (0.0, 50000.0)]
        res = series.step(xy, "sentinel2")
        self.assertEqual(res, 250)
        self.assertLessEqual(50000.0 / res, series.SERIES_PIXELS)


class TestPoint(unittest.TestCase):

    def test_median_and_band_over_clear_pixels(self):
        values = np.arange(100, dtype=np.float32).reshape(10, 10)
        area = np.ones((10, 10), dtype=bool)
        clear = np.ones((10, 10), dtype=bool)
        clear[:, 5:] = False  # облако на правой половине
        p = series.point(values, area, clear)
        self.assertAlmostEqual(p.share, 50.0)
        expected = values[:, :5].astype(np.float64)
        self.assertAlmostEqual(p.median, float(np.median(expected)))
        self.assertAlmostEqual(p.low, float(np.percentile(expected, 10)))
        self.assertAlmostEqual(p.high, float(np.percentile(expected, 90)))

    def test_nan_counts_as_missing(self):
        values = np.full((10, 10), np.nan, dtype=np.float32)
        values[0, :9] = 0.5
        area = np.ones((10, 10), dtype=bool)
        self.assertIsNone(series.point(values, area, area))
        values[1, :] = 0.7
        p = series.point(values, area, area)
        self.assertAlmostEqual(p.share, 19.0)

    def test_outside_area_is_ignored(self):
        values = np.zeros((4, 4), dtype=np.float32)
        values[0, 0] = 100.0
        area = np.ones((4, 4), dtype=bool)
        area[0, 0] = False
        p = series.point(values, area, np.ones((4, 4), dtype=bool))
        self.assertEqual(p.high, 0.0)

    def test_empty_area(self):
        self.assertIsNone(series.point(np.zeros((2, 2)),
                                       np.zeros((2, 2), dtype=bool),
                                       np.ones((2, 2), dtype=bool)))


class TestDates(unittest.TestCase):

    def test_day_number(self):
        self.assertEqual(series.day_number("1970-01-02"), 1.0)
        self.assertAlmostEqual(series.day_number("1970-01-01 12:00"), 0.5)

    def test_year_ticks(self):
        first = series.day_number("2016-03-05")
        last = series.day_number("2026-10-01")
        ticks = series.date_ticks(first, last)
        self.assertTrue(all(label.isdigit() for _, label in ticks))
        self.assertLessEqual(len(ticks), 6)
        self.assertGreaterEqual(ticks[0][0], first)
        self.assertLessEqual(ticks[-1][0], last)

    def test_month_ticks_start_on_first_day(self):
        first = series.day_number("2024-01-17")
        last = series.day_number("2024-12-20")
        ticks = series.date_ticks(first, last)
        self.assertEqual(ticks[0][1], "2024-03")
        self.assertTrue(all(len(label) == 7 for _, label in ticks))

    def test_day_ticks(self):
        first = series.day_number("2024-06-01")
        last = series.day_number("2024-06-20")
        ticks = series.date_ticks(first, last)
        self.assertEqual(ticks[0][1], "2024-06-01")
        self.assertLessEqual(len(ticks), 6)


class TestCsv(unittest.TestCase):

    def test_rows(self):
        text = series.csv_text(
            [("2024-06-01 10:00", "S2A_1", series.Point(0.5, 0.4, 0.6,
                                                       80.0)),
             ("2024-06-06 10:00", "S2B_2", None)], "NDVI")
        lines = text.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[1],
                         '2024-06-01 10:00,S2A_1,0.5000,0.4000,0.6000,80.0,'
                         '"NDVI"')
        self.assertEqual(lines[2], '2024-06-06 10:00,S2B_2,,,,,"NDVI"')


if __name__ == "__main__":
    unittest.main()
