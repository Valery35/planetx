# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/aurora.py: разбор прогноза OVATION."""
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import aurora as au  # noqa: E402
import weather as w  # noqa: E402


def sample_file(value=40):
    """Файл в разметке OVATION: тройки долгота, широта, вероятность."""
    triples = [[lon, lat, value if lat == 67 and lon == 30 else 0]
               for lon in range(360) for lat in range(-90, 91)]
    return json.dumps({"Observation Time": "2026-10-12T03:10:00Z",
                       "Forecast Time": "2026-10-12T03:45:00Z",
                       "Data Format": "[Longitude, Latitude, Aurora]",
                       "coordinates": triples}).encode("utf-8")


class TestParse(unittest.TestCase):

    def test_grid_rows_north_to_south(self):
        grid = au.parse(sample_file())
        self.assertEqual(grid.values.shape, (181, 360))
        self.assertEqual(grid.values[90 - 67, 30], 40.0)
        self.assertEqual(float(grid.values.sum()), 40.0)
        self.assertEqual(au.valid_text(grid), "2026-10-12 03:45")

    def test_sample_at_point_and_west_longitude(self):
        grid = au.parse(sample_file())
        value = w.sample(grid, np.array([67.0]), np.array([30.0]))
        self.assertAlmostEqual(float(value[0]), 40.0)
        # Западная долгота -330° - та же точка.
        value = w.sample(grid, np.array([67.0]), np.array([-330.0]))
        self.assertAlmostEqual(float(value[0]), 40.0)

    def test_weak_aurora_is_clear(self):
        rgba = w.colorize(au.FIELD, np.array([1.0, 50.0]))
        self.assertEqual(rgba[0][3], 0)
        self.assertGreater(rgba[1][3], 200)

    def test_bad_files_refused(self):
        self.assertIsNone(au.parse(b"<html>"))
        self.assertIsNone(au.parse(b"{}"))
        self.assertIsNone(au.parse(json.dumps(
            {"coordinates": [[0, 0, 1]]}).encode()))

    def test_forecast_time_forms(self):
        self.assertEqual(au.forecast_seconds("2026-10-12T03:45:00Z"),
                         au.forecast_seconds("2026-10-12 03:45"))
        self.assertIsNone(au.forecast_seconds("вчера"))


if __name__ == "__main__":
    unittest.main()
