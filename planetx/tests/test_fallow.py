# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты заросших полей (core/fallow.py)."""
import os
import sys
import unittest
from collections import namedtuple

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import fallow  # noqa: E402
import objecttasks as ot  # noqa: E402

ROLES = ["swir2", "nir", "red"]  # сочетание «SWIR» B12 B8A B4
Scene = namedtuple("Scene", "when")


def scene(red, nir, swir=0.2, shape=(10, 10)):
    return np.stack([np.full(shape, swir), np.full(shape, nir),
                     np.full(shape, red)])


class TestBare(unittest.TestCase):
    def test_ploughed_soil_bare_thatch_and_grass_not(self):
        # Числа снимков у Шадейки: пашня, сухая ветошь, всходы.
        self.assertEqual(fallow.bare_cells(scene(0.12, 0.17), ROLES)[0, 0],
                         1.0)
        self.assertEqual(fallow.bare_cells(scene(0.09, 0.20), ROLES)[0, 0],
                         0.0)
        self.assertEqual(fallow.bare_cells(scene(0.04, 0.35), ROLES)[0, 0],
                         0.0)

    def test_water_and_snow_unknown(self):
        self.assertTrue(np.isnan(
            fallow.bare_cells(scene(0.03, 0.03), ROLES)[0, 0]))
        self.assertTrue(np.isnan(
            fallow.bare_cells(scene(0.8, 0.8, 0.05), ROLES)[0, 0]))

    def test_needs_red_and_nir(self):
        self.assertIsNone(fallow.bare_cells(scene(0.1, 0.2),
                                            ["swir1", "nir", "blue"]))


class TestWoody(unittest.TestCase):
    def test_forest_dark_in_swir_meadow_light(self):
        # Числа Шадейки: лес 0.03-0.08, луг 0.10-0.20 по SWIR 2,2 мкм.
        forest = [scene(0.04, 0.30, 0.05), scene(0.05, 0.28, 0.07)]
        meadow = [scene(0.06, 0.30, 0.14), scene(0.05, 0.32, 0.12)]
        both = [(np.concatenate([f, m], axis=2), ROLES)
                for f, m in zip(forest, meadow)]
        trees = fallow.season_woody(both)
        self.assertTrue((trees[:, :10] == 1.0).all())
        self.assertTrue((trees[:, 10:] == 0.0).all())

    def test_snow_does_not_count(self):
        snowy = scene(0.8, 0.8, 0.02)  # тёмный в SWIR снег - не лес
        trees = fallow.season_woody([(snowy, ROLES)])
        self.assertTrue(np.isnan(trees).all())

    def test_no_swir_gives_none(self):
        self.assertIsNone(fallow.season_woody(
            [(scene(0.1, 0.3)[1:], ["nir", "red"])]))


class TestYears(unittest.TestCase):
    def setUp(self):
        # Четыре поля по 10 клеток: 0 - пашня каждый год, 1 - брошено
        # после 2023 года, 2 - не пахалось, 3 - деревня всегда голая.
        self.parts = np.repeat(np.arange(4), 10).reshape(4, 10)
        self.scenes = []
        for year in (2023, 2024, 2025, 2026):
            cells = np.zeros((4, 10))
            cells[0] = 1.0
            cells[1] = 1.0 if year == 2023 else 0.0
            cells[3] = 1.0
            self.scenes.append((year, cells))

    def test_last_year_and_kinds(self):
        years, bare, seen = fallow.tilled_years(self.parts, self.scenes, 4)
        woody = np.array([0.0, 0.0, 0.05, 0.0])
        summer = [ot.VEGETATION] * 3 + [ot.SOIL]
        kinds, last = fallow.field_kinds(summer, years, bare, seen, woody,
                                         2026)
        self.assertEqual(last, [2026, 2023, 0, 2026])
        self.assertEqual(kinds, [fallow.TILLED, fallow.FALLOW_OLD,
                                 fallow.FALLOW_OLD, ot.SOIL])

    def test_recent_abandonment_and_trees(self):
        scenes = [(y, c.copy()) for y, c in self.scenes]
        scenes[2][1][1] = 1.0  # поле 1 пахали и в 2025 году
        years, bare, seen = fallow.tilled_years(self.parts, scenes, 4)
        woody = np.array([0.0, 0.0, 0.4, 0.0])
        kinds, _ = fallow.field_kinds([ot.VEGETATION] * 4, years, bare,
                                      seen, woody, 2026)
        self.assertEqual(kinds[1], fallow.FALLOW_NEW)
        self.assertEqual(kinds[2], fallow.OVERGROWN)
        woody[2] = 0.9
        kinds, _ = fallow.field_kinds([ot.VEGETATION] * 4, years, bare,
                                      seen, woody, 2026)
        self.assertEqual(kinds[2], fallow.FOREST)

    def test_scene_without_data_on_field_is_not_counted(self):
        scenes = [(y, c.copy()) for y, c in self.scenes]
        scenes[3][1][0] = np.nan  # 2026 год над пашней - снег
        years, _, seen = fallow.tilled_years(self.parts, scenes, 4)
        self.assertNotIn(2026, years[0])
        self.assertEqual(seen[0], 3)

    def test_water_stays_water(self):
        years, bare, seen = fallow.tilled_years(self.parts, self.scenes, 4)
        kinds, _ = fallow.field_kinds([ot.WATER] * 4, years, bare, seen,
                                      None, 2026)
        self.assertEqual(kinds, [ot.WATER] * 4)


class TestPick(unittest.TestCase):
    def test_best_scene_per_year_and_season(self):
        found = [(Scene("2025-05-07"), 0.0, 100), (Scene("2025-05-29"), 1.0,
                                                     100),
                 (Scene("2025-04-20"), 0.0, 100), (Scene("2025-09-01"), 0.0,
                                                     100),
                 (Scene("2025-09-19"), 1.0, 100), (Scene("2025-05-24"), 5.0,
                                                     100),
                 (Scene("2024-10-14"), 0.0, 100), (Scene("2024-07-01"), 0.0,
                                                     100)]
        out = fallow.pick(found)
        self.assertEqual(out[(2025, "spring")][0][0].when, "2025-05-29")
        self.assertEqual(out[(2025, "autumn")][0][0].when, "2025-09-19")
        self.assertEqual(out[(2024, "autumn")][0][0].when, "2024-10-14")
        self.assertNotIn((2024, "spring"), out)


if __name__ == "__main__":
    unittest.main()
