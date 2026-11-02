# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Минералы по спектру: каналы по подписям, угол, классы, библиотека."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import spectra  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "spectra.json")


class TestLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = spectra.load(DATA)

    def test_sensors_and_groups(self):
        self.assertEqual(len(self.lib.sensors["aster"]["um"]), 9)
        self.assertEqual(len(self.lib.sensors["landsat8"]["um"]), 7)
        self.assertEqual(len(self.lib.sensors["sentinel2"]["um"]), 13)
        groups = {s["group"] for s in self.lib.spectra}
        self.assertLessEqual(groups, set(spectra.GROUPS))
        self.assertIn("minerals", groups)

    def test_kaolinite_dips_at_aster_band_6(self):
        # Каолинит поглощает у 2.2 мкм: канал 6 ASTER ниже канала 4.
        found = spectra.search(self.lib, "kaolinite cm3")
        self.assertTrue(found)
        values = found[0]["aster"]
        self.assertLess(values[5], values[3] * 0.8)

    def test_aster_file_labels_match_aster(self):
        labels = ["B1 0.56 um", "B2 0.66 um", "B3N 0.82 um", "B4 1.65 um",
                  "B5 2.165 um", "B6 2.205 um", "B7 2.26 um", "B8 2.33 um",
                  "B9 2.395 um", "B10 8.3 um, K", "B11 8.65 um, K"]
        sensor, pairs = spectra.pairs_for(self.lib, labels)
        self.assertEqual(sensor, "aster")
        self.assertEqual(pairs, [(n, n) for n in range(9)])

    def test_sentinel_and_landsat_names(self):
        s2 = ["B1 coastal", "B2 blue", "B3 green", "B4 red",
              "B5 rededge1", "B6 rededge2", "B7 rededge3", "B8 nir",
              "B8A nir08", "B9 nir09", "B11 swir16", "B12 swir22"]
        sensor, pairs = spectra.pairs_for(self.lib, s2)
        self.assertEqual(sensor, "sentinel2")
        self.assertEqual(len(pairs), 12)
        self.assertIn((10, 11), pairs)  # B11 - 12-й канал библиотеки
        landsat = ["B1 coastal", "B2 blue", "B3 green", "B4 red",
                   "B5 nir08", "B6 swir16", "B7 swir22", "B10 lwir, K"]
        sensor, pairs = spectra.pairs_for(self.lib, landsat)
        self.assertEqual(sensor, "landsat8")
        self.assertEqual(pairs, [(n, n) for n in range(7)])

    def test_unknown_labels_need_sensor(self):
        labels = ["Band 1", "Band 2", "Band 3", "Band 4"]
        self.assertEqual(spectra.pairs_for(self.lib, labels), (None, []))
        sensor, pairs = spectra.pairs_for(self.lib, labels, "landsat8")
        self.assertEqual(sensor, "landsat8")
        self.assertEqual(pairs, [(0, 0), (1, 1), (2, 2), (3, 3)])
        s2 = ["B2", "B3", "B4", "B8A", "B11"]
        self.assertEqual(spectra.pairs_for(self.lib, s2, "sentinel2")[1],
                         [(0, 1), (1, 2), (2, 3), (3, 8), (4, 11)])

    def test_wavelength_units(self):
        self.assertAlmostEqual(spectra.wavelength("665 nm"), 0.665)
        self.assertAlmostEqual(spectra.wavelength("B4 1.65 um"), 1.65)
        self.assertIsNone(spectra.wavelength("B13 10.6 um, K"))
        self.assertIsNone(spectra.wavelength("Band 1"))


class TestAngle(unittest.TestCase):
    def test_brightness_does_not_change_angle(self):
        ref = np.array([[0.2, 0.4, 0.3, 0.1]])
        cube = np.array([[0.2, 0.1], [0.4, 0.2], [0.3, 0.15],
                         [0.1, 0.05]])
        out = spectra.angles(cube, ref)
        self.assertLess(float(np.nanmax(out)), 1e-3)

    def test_classify_picks_nearest_within_limit(self):
        refs = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        grid = np.zeros((3, 1, 4))
        grid[:, 0, 0] = (1.0, 0.05, 0.0)    # к первому, угол 2.9°
        grid[:, 0, 1] = (0.05, 1.0, 0.0)    # ко второму
        grid[:, 0, 2] = (1.0, 1.0, 1.0)     # далеко от обоих
        grid[:, 0, 3] = np.nan              # нет данных
        kinds, angle = spectra.classify(grid, refs, limit=6.0)
        self.assertEqual(kinds[0].tolist(), [0, 1, -1, -1])
        self.assertAlmostEqual(float(angle[0, 0]), 2.862, places=2)
        self.assertTrue(np.isnan(angle[0, 3]))

    def test_nearest_and_scaled(self):
        refs = np.array([[1.0, 2.0, 3.0], [3.0, 2.0, 1.0]])
        spectrum = np.array([0.5, 1.0, 1.6])
        found = spectra.nearest(spectrum, refs, 2)
        self.assertEqual(found[0][0], 0)
        self.assertLess(found[0][1], found[1][1])
        fitted = spectra.scaled(refs[0], spectrum)
        self.assertAlmostEqual(float(fitted[1]), 1.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
