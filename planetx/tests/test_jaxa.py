# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Наборы JAXA Earth по участку: адреса, квадраты, сетка, значения,
ряд по месяцам."""
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import jaxa  # noqa: E402

NDVI = jaxa.BY_KEY["ndvi"]
STEP = NDVI.step
SIDE = int(round(jaxa.QUAD / STEP))


def world_block(fill, step=STEP):
    """block для read_grid: число файла пикселя - fill(мировой столбец,
    мировая строка) по нумерации от -180 и 90."""
    calls = []

    def block(west, south, c0, r0, c1, r1):
        calls.append((west, south, c0, r0, c1, r1))
        qc0 = int(round((west + 180.0) / step))
        qr0 = int(round((90.0 - south - jaxa.QUAD) / step))
        cols = np.arange(c0, c1 + 1) + qc0
        rows = np.arange(r0, r1 + 1) + qr0
        cc, rr = np.meshgrid(cols, rows)
        return fill(cc, rr).astype(np.float64)
    return block, calls


class TestUrls(unittest.TestCase):

    def test_north_east_quad(self):
        self.assertEqual(
            jaxa.quad_url(NDVI, "2026-07", 0.0, 0.0),
            jaxa.ROOT + NDVI.id + "/2026-07/1/E000.00-E090.00/"
            "E000.00-N00.00-E090.00-N90.00-NDVI.tiff")

    def test_south_west_quad(self):
        # Имя файла сверено с каталогом набора 9 ноября 2026 года.
        self.assertEqual(
            jaxa.quad_url(NDVI, "2026-07", -180.0, -90.0),
            jaxa.ROOT + NDVI.id + "/2026-07/1/W180.00-W090.00/"
            "W180.00-S90.00-W090.00-N00.00-NDVI.tiff")

    def test_quad_ending_at_greenwich(self):
        self.assertIn("/W090.00-E000.00/W090.00-N00.00-E000.00-N90.00-",
                      jaxa.quad_url(NDVI, "2026-07", -90.0, 0.0))

    def test_collection(self):
        self.assertTrue(jaxa.collection_url(NDVI).endswith(
            NDVI.id + "/collection.json"))


class TestQuads(unittest.TestCase):

    def test_one_quad(self):
        self.assertEqual(jaxa.quads((37.0, 55.0, 38.0, 56.0)), [(0.0, 0.0)])

    def test_greenwich_and_equator(self):
        self.assertEqual(sorted(jaxa.quads((-1.0, -1.0, 1.0, 1.0))),
                         [(-90.0, -90.0), (-90.0, 0.0), (0.0, -90.0),
                          (0.0, 0.0)])

    def test_date_line(self):
        self.assertEqual(sorted(jaxa.quads((179.0, 60.0, -179.0, 61.0))),
                         [(-180.0, 0.0), (90.0, 0.0)])

    def test_edge_is_not_a_quad(self):
        self.assertEqual(jaxa.quads((0.0, 10.0, 10.0, 20.0)), [(0.0, 0.0)])


class TestGrid(unittest.TestCase):

    def test_nodes_on_pixel_centres(self):
        grid = jaxa.grid_for((37.01, 55.01, 37.09, 55.04), STEP)
        self.assertAlmostEqual(grid.west, 37.0125)
        self.assertAlmostEqual(grid.north, 55.0375)
        self.assertEqual((grid.rows, grid.cols), (2, 4))

    def test_tiny_box_is_one_pixel(self):
        grid = jaxa.grid_for((37.001, 55.001, 37.002, 55.002), STEP)
        self.assertEqual((grid.rows, grid.cols), (1, 1))

    def test_small_area_takes_its_centre(self):
        grid = jaxa.grid_for((37.0, 55.0, 37.075, 55.075), STEP)
        mask = jaxa.area_mask(grid, lambda lats, lons:
                              np.zeros(lats.shape, dtype=bool))
        self.assertEqual(int(mask.sum()), 1)
        self.assertTrue(mask[1, 1])


class TestValues(unittest.TestCase):

    def test_scale_and_empty(self):
        out = jaxa.to_values(NDVI, [0.0, 10000.0, 18000.0, 65535.0,
                                    np.nan])
        self.assertAlmostEqual(out[0], -1.0)
        self.assertAlmostEqual(out[1], 0.0)
        self.assertAlmostEqual(out[2], 0.8)
        self.assertTrue(np.isnan(out[3]) and np.isnan(out[4]))

    def test_temperature_in_celsius(self):
        lst = jaxa.BY_KEY["lst"]
        self.assertAlmostEqual(jaxa.to_values(lst, [14657.5])[0], 20.0)

    def test_precipitation_error_codes(self):
        rain = jaxa.BY_KEY["precip"]
        out = jaxa.to_values(rain, [-999.9, -4.0, -8.0, -99.0, 0.25])
        self.assertEqual(int(np.isnan(out).sum()), 4)
        self.assertAlmostEqual(out[4], 0.25)

    def test_every_set_has_ramp_and_band(self):
        for dataset in jaxa.SETS:
            self.assertTrue(dataset.band and dataset.stops, dataset.key)
            levels = [v for v, _ in dataset.stops]
            self.assertEqual(levels, sorted(levels), dataset.key)


class TestDates(unittest.TestCase):

    def test_children_sorted(self):
        text = json.dumps({"links": [
            {"rel": "child", "href": "./2026-10/catalog.json"},
            {"rel": "child", "href": "./2018-01/catalog.json"},
            {"rel": "root", "href": "./2019-01/catalog.json"},
            {"rel": "child", "href": "./2018-13/catalog.json"},
            {"rel": "child", "href": "./2018/catalog.json"},
            {"rel": "child", "href": 5},
            "junk"]})
        self.assertEqual(jaxa.parse_dates(text), ["2018-01", "2026-10"])

    def test_hostile_answers(self):
        for text in ("", "<html>", "[]", '{"links": 5}', None):
            self.assertEqual(jaxa.parse_dates(text), [])

    def test_between(self):
        dates = ["2025-11", "2025-12", "2026-01", "2026-02"]
        self.assertEqual(jaxa.between(dates, "2025-12", "2026-01"),
                         ["2025-12", "2026-01"])

    def test_month_middle(self):
        self.assertAlmostEqual(jaxa.month_day("1970-01"), 14.5)
        self.assertIsNone(jaxa.month_day("1970-00"))


class TestReadGrid(unittest.TestCase):

    def test_one_quad_values(self):
        grid = jaxa.grid_for((37.0, 55.0, 37.1, 55.05), STEP)
        block, calls = world_block(lambda c, r: 10000.0 + c)
        values = jaxa.read_grid(NDVI, grid, block)
        self.assertEqual(len(calls), 1)
        first = int(round((37.0 + 180.0) / STEP))
        self.assertAlmostEqual(values[0, 0], first * 1e-4)
        self.assertAlmostEqual(values[1, 3], (first + 3) * 1e-4)

    def test_across_greenwich(self):
        grid = jaxa.grid_for((-0.05, 51.0, 0.05, 51.025), STEP)
        block, calls = world_block(lambda c, r: 10000.0 + c)
        values = jaxa.read_grid(NDVI, grid, block)
        self.assertEqual(sorted(c[0] for c in calls), [-90.0, 0.0])
        west = [c for c in calls if c[0] == -90.0][0]
        self.assertEqual((west[2], west[4]), (SIDE - 2, SIDE - 1))
        self.assertTrue(np.isfinite(values).all())
        steps = np.diff(values[0])
        self.assertTrue(np.allclose(steps, 1e-4))

    def test_coarse_set_has_its_own_grid(self):
        # У осадков пиксель 0.1°: сетка 0.025° читала бы не те пиксели.
        rain = jaxa.BY_KEY["precip"]
        grid = jaxa.grid_for((37.3, 55.5, 37.9, 55.9), rain.step)
        self.assertEqual((grid.rows, grid.cols), (4, 6))
        self.assertAlmostEqual(grid.west, 37.35)
        block, calls = world_block(lambda c, r: 0.1 * c, rain.step)
        values = jaxa.read_grid(rain, grid, block)
        first = int(round((37.3 + 180.0) / rain.step))
        self.assertEqual(calls[0][2], first - int(round(180.0 / rain.step)))
        self.assertAlmostEqual(values[0, 0], 0.1 * first)

    def test_step_fits(self):
        self.assertTrue(jaxa.step_fits(NDVI, (0, 0.025, 0, 90, 0, -0.025)))
        self.assertFalse(jaxa.step_fits(NDVI, (0, 0.1, 0, 90, 0, -0.1)))
        self.assertTrue(jaxa.step_fits(jaxa.BY_KEY["aod"],
                                       (0, 0.05, 0, 90, 0, -0.05)))

    def test_missing_file_stays_empty(self):
        grid = jaxa.grid_for((-0.05, 51.0, 0.05, 51.025), STEP)

        def block(west, south, c0, r0, c1, r1):
            if west < 0:
                return None
            return np.full((r1 - r0 + 1, c1 - c0 + 1), 12000.0)
        values = jaxa.read_grid(NDVI, grid, block)
        self.assertTrue(np.isnan(values[:, :2]).all())
        self.assertTrue(np.allclose(values[:, 2:], 0.2))

    def test_south_rows(self):
        grid = jaxa.grid_for((20.0, -0.05, 20.025, 0.05), STEP)
        block, calls = world_block(lambda c, r: 10000.0 + r)
        values = jaxa.read_grid(NDVI, grid, block)
        self.assertEqual(sorted(c[1] for c in calls), [-90.0, 0.0])
        self.assertTrue(np.allclose(np.diff(values[:, 0]), 1e-4))


class TestMonth(unittest.TestCase):

    def test_point_over_area_only(self):
        grid = jaxa.grid_for((37.0, 55.0, 37.25, 55.25), STEP)
        block, _ = world_block(lambda c, r: 10000.0 + 1000.0 * (c % 2))
        mask = np.zeros((grid.rows, grid.cols), dtype=bool)
        mask[:, ::2] = True
        month = jaxa.month_of(NDVI, "2026-07", grid, mask, block)
        self.assertEqual(month.date, "2026-07")
        values = month.values[mask]
        self.assertTrue(np.isnan(month.values[~mask]).all())
        self.assertAlmostEqual(month.point.median, float(np.median(values)))
        self.assertAlmostEqual(month.point.share, 100.0)

    def test_empty_month_has_no_point(self):
        grid = jaxa.grid_for((37.0, 55.0, 37.25, 55.25), STEP)
        mask = np.ones((grid.rows, grid.cols), dtype=bool)
        month = jaxa.month_of(NDVI, "2026-01", grid, mask, lambda *a: None)
        self.assertIsNone(month.point)

    def test_same_month(self):
        months = [jaxa.Month(d, jaxa.month_day(d), None, None)
                  for d in ("2024-07", "2024-08", "2025-07")]
        self.assertEqual([m.date for m in jaxa.same_month(months, "2026-07")],
                         ["2024-07", "2025-07"])

    def test_csv(self):
        grid = jaxa.grid_for((37.0, 55.0, 37.1, 55.1), STEP)
        mask = np.ones((grid.rows, grid.cols), dtype=bool)
        block, _ = world_block(lambda c, r: np.full(c.shape, 15000.0))
        months = [jaxa.month_of(NDVI, "2026-07", grid, mask, block),
                  jaxa.month_of(NDVI, "2026-08", grid, mask,
                                lambda *a: None)]
        lines = jaxa.csv_text(NDVI, months, "NDVI").splitlines()
        self.assertEqual(lines[0], "month,band,median,p10,p90,"
                                   "valid_percent,product")
        self.assertTrue(lines[1].startswith("2026-07,NDVI,0.5000,"))
        self.assertEqual(lines[2], '2026-08,NDVI,,,,,"NDVI"')


if __name__ == "__main__":
    unittest.main()
