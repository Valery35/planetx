# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Своя батиметрия: глубины в отметки дна, настройки, сетка воды."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import bathymetry  # noqa: E402


class TestBathymetry(unittest.TestCase):
    def test_depths_become_bed_either_sign(self):
        bed = bathymetry.to_bed(np.array([10.0, -10.0, np.nan, 0.0]),
                                "depth", 564.0)
        self.assertEqual(list(bed[:2]), [554.0, 554.0])
        self.assertTrue(np.isnan(bed[2]))
        self.assertEqual(bed[3], 564.0)
        same = bathymetry.to_bed(np.array([308.0]), "bed", 564.0)
        self.assertEqual(float(same[0]), 308.0)

    def test_settings_round_trip(self):
        settings = {"layer_a": ("depth", 456.5), "layer_b": ("bed", 564.0)}
        self.assertEqual(bathymetry.parse(bathymetry.dump(settings)),
                         settings)
        self.assertEqual(bathymetry.parse("not json"), {})
        self.assertEqual(bathymetry.parse('{"x": {"kind": "sea"}}'), {})

    def test_water_over_wet_nodes_only(self):
        # Сетка 3 × 3: левый столбец - берег выше воды, прочие - дно.
        bed = np.array([[600.0, 500.0, 480.0],
                        [600.0, 450.0, 470.0],
                        [600.0, 500.0, np.nan]])
        lats, lons = np.meshgrid([46.73, 46.72, 46.71],
                                 [7.95, 7.96, 7.97], indexing="ij")
        part = bathymetry.water_part(lats, lons, bed, 564.0, 564.0)
        self.assertIsNotNone(part)
        used = set(part.indices.ravel().tolist())
        self.assertFalse(used & {0, 3, 6})  # берег без воды
        self.assertNotIn(8, used)  # пустой узел
        self.assertEqual(len(part.indices), 3)  # 2 + 1 треугольник
        self.assertIsNone(bathymetry.water_part(lats, lons, bed + 200.0,
                                                564.0, 564.0))

    def test_mercator_back_to_degrees(self):
        lat, lon = bathymetry.mercator_latlon(0.0, 0.0)
        self.assertAlmostEqual(float(lat), 0.0)
        lat, lon = bathymetry.mercator_latlon(885725.0, 5897250.0)
        self.assertAlmostEqual(float(lon), 7.9566, places=3)
        self.assertAlmostEqual(float(lat), 46.75, places=1)


if __name__ == "__main__":
    unittest.main()
