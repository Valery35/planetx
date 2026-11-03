# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты типовых задач выделения объектов (core/objecttasks.py)."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import objecttasks as ot  # noqa: E402

# Средние отражения цвета в сочетании «Сельское хозяйство»: SWIR1, NIR,
# синий.
AGRI = ["swir1", "nir", "blue"]
CONIFER = [0.08, 0.20, 0.02]
BROADLEAF = [0.17, 0.38, 0.03]
SOIL = [0.30, 0.22, 0.08]
WATER = [0.01, 0.02, 0.04]
SNOW = [0.10, 0.70, 0.80]


class TestChannels(unittest.TestCase):
    def test_descriptions_give_roles(self):
        self.assertEqual(ot.channels(["B11 swir16", "B8 nir", "B2 blue"],
                                     "x"), AGRI)

    def test_file_name_of_composite(self):
        self.assertEqual(ot.channels(["", "", ""],
                                     "S2_20240701_40VDK_agriculture"), AGRI)
        self.assertEqual(ot.channels(None,
                                     "L9_20250923_166-020_infrared_2"),
                         ["nir", "red", "green"])
        self.assertEqual(ot.month_of("S2_20240701_40VDK_agriculture"), 7)
        self.assertEqual(ot.day_of("S2_20240701_40VDK_agriculture_2"),
                         "2024-07-01")
        self.assertIsNone(ot.day_of("ortho"))
        self.assertEqual(ot.role_names(["nir", None, "red", "nir"]),
                         ["nir", "red"])

    def test_unknown_raster_has_no_roles(self):
        self.assertIsNone(ot.channels(["Band 1"], "ortho"))
        self.assertFalse(ot.usable(None))
        self.assertFalse(ot.usable(["red", "green", "blue"]))
        self.assertTrue(ot.usable(AGRI))


class TestKinds(unittest.TestCase):
    def test_agriculture_composite(self):
        kinds = ot.color_kinds([CONIFER, BROADLEAF, SOIL, WATER, SNOW],
                               AGRI)
        self.assertEqual(kinds, [ot.CONIFER, ot.BROADLEAF, ot.SOIL,
                                 ot.WATER, ot.SNOW])

    def test_infrared_composite_by_ndvi(self):
        # NIR, красный, зелёный: лес, пашня, вода.
        kinds = ot.color_kinds([[0.35, 0.04, 0.06], [0.22, 0.18, 0.14],
                                [0.02, 0.03, 0.05]], ["nir", "red", "green"])
        self.assertEqual(kinds, [ot.VEGETATION, ot.SOIL, ot.WATER])

    def test_close_vegetation_is_not_split(self):
        kinds = ot.color_kinds([[0.17, 0.36, 0.03], [0.16, 0.38, 0.03]],
                               AGRI)
        self.assertEqual(kinds, [ot.VEGETATION, ot.VEGETATION])

    def test_scenario_merges(self):
        kinds = [ot.CONIFER, ot.BROADLEAF, ot.SOIL, ot.WATER]
        self.assertEqual(ot.scenario_kinds(kinds, "fields"),
                         [ot.VEGETATION, ot.VEGETATION, ot.SOIL, ot.WATER])
        self.assertEqual(ot.scenario_kinds(kinds, "water"),
                         [ot.OTHER, ot.OTHER, ot.OTHER, ot.WATER])


class TestTwoDates(unittest.TestCase):
    def test_leaf_off_tells_conifer(self):
        # Лето: хвоя и листва одной яркости ИК (одним снимком не
        # различить), осень: листва потеряла ИК, хвоя нет.
        summer = [[0.17, 0.32, 0.03], [0.17, 0.33, 0.03], SOIL]
        autumn = [[0.15, 0.29, 0.03], [0.20, 0.14, 0.04], SOIL]
        centers = np.hstack([summer, autumn])
        kinds = ot.color_kinds(np.array(summer), AGRI)
        self.assertEqual(kinds, [ot.VEGETATION, ot.VEGETATION, ot.SOIL])
        both = ot.two_dates(kinds, centers, AGRI, AGRI)
        self.assertEqual(both, [ot.CONIFER, ot.BROADLEAF, ot.SOIL])

    def test_snow_tells_conifer(self):
        # Март: хвоя тёмная на снегу, голый лиственный лес светлый, поле -
        # снег. У снега ближний ИК высокий - правило ИК дало бы хвою и
        # листве.
        summer = [[0.17, 0.32, 0.03], [0.17, 0.33, 0.03], SOIL]
        march = [[0.10, 0.22, 0.12], [0.18, 0.55, 0.45],
                 [0.08, 0.80, 0.85]]
        centers = np.hstack([summer, march])
        kinds = ot.color_kinds(np.array(summer), AGRI)
        self.assertIsNotNone(ot.winter(centers, AGRI, AGRI))
        both = ot.two_dates(kinds, centers, AGRI, AGRI)
        self.assertEqual(both, [ot.CONIFER, ot.BROADLEAF, ot.SOIL])

    def test_snow_and_summer_nir_together(self):
        # Числа снимков 21 июля 2025 и 17 апреля 2026 года у 59.99,
        # 57.43. Голый лиственный лес тёмный на снегу, но летом ярок
        # в ИК - листва. Тёмный летом и светлый на снегу - не хвоя.
        summer = [[0.134, 0.329, 0.027], [0.114, 0.279, 0.026],
                  [0.093, 0.216, 0.026], [0.203, 0.468, 0.035],
                  [0.09, 0.21, 0.03]]
        april = [[0.082, 0.22, 0.11], [0.068, 0.188, 0.053],
                 [0.056, 0.159, 0.02], [0.056, 0.531, 0.532],
                 [0.06, 0.6, 0.55]]
        centers = np.hstack([summer, april])
        kinds = ot.color_kinds(np.array(summer), AGRI)
        both = ot.two_dates(kinds, centers, AGRI, AGRI)
        self.assertEqual(both, [ot.BROADLEAF, ot.CONIFER, ot.CONIFER,
                                ot.BROADLEAF, ot.BROADLEAF])

    def test_no_snow_keeps_nir_rule(self):
        centers = np.hstack([[[0.17, 0.32, 0.03]], [[0.15, 0.29, 0.03]]])
        self.assertIsNone(ot.winter(centers, AGRI, AGRI))

    def test_second_without_nir_changes_nothing(self):
        kinds = [ot.VEGETATION, ot.SOIL]
        self.assertEqual(ot.two_dates(kinds, np.zeros((2, 6)), AGRI,
                                      ["red", "green", "blue"]), kinds)


class TestClearing(unittest.TestCase):
    def setUp(self):
        # Слева лес (0), в нём вырубка (1), справа поле (2) среди пашни
        # без леса.
        parts = np.zeros((10, 20), dtype=np.int64)
        parts[3:6, 3:6] = 1
        parts[:, 10:] = 2
        self.parts = parts

    def test_soil_in_forest_is_clearing(self):
        kinds = [ot.CONIFER, ot.SOIL]
        out = ot.region_kinds(self.parts, [0, 1, 1], kinds, "forest")
        self.assertEqual(out[1], ot.CLEARING)
        out = ot.region_kinds(self.parts, [0, 1, 1], kinds, "fields")
        self.assertEqual(out[1], ot.CLEARING)

    def test_clearing_of_two_soil_shades(self):
        # Вырубка из двух оттенков почвы (1 и 2): каждая половина
        # граничит больше с другой, чем с лесом, кусок - весь в лесу.
        parts = np.zeros((20, 20), dtype=np.int64)
        parts[5:15, 5:10] = 1
        parts[5:15, 10:15] = 2
        out = ot.region_kinds(parts, [0, 1, 2],
                              [ot.CONIFER, ot.SOIL, ot.SOIL], "forest")
        self.assertEqual(out, [ot.CONIFER, ot.CLEARING, ot.CLEARING])

    def test_field_next_to_crops_stays_soil(self):
        # Пашня (0) у посева (1) - светлой растительности, хвои нет.
        parts = np.zeros((10, 20), dtype=np.int64)
        parts[:, 10:] = 1
        out = ot.region_kinds(parts, [0, 1], [ot.SOIL, ot.BROADLEAF],
                              "forest")
        self.assertEqual(out, [ot.SOIL, ot.BROADLEAF])

    def test_field_with_little_forest_border_stays_soil(self):
        # Пашня 0 граничит с посевом 1 длинной стороной и с хвоей 2 - углом.
        parts = np.ones((20, 20), dtype=np.int64)
        parts[:, :10] = 0
        parts[:2, 10:12] = 2
        out = ot.region_kinds(parts, [0, 1, 2],
                              [ot.SOIL, ot.BROADLEAF, ot.CONIFER], "forest")
        self.assertEqual(out[0], ot.SOIL)

    def test_thin_conifer_rim_is_not_forest(self):
        # Поле (1) в кольце смешанных пикселей «хвои» (2) шириной
        # в клетку среди листвы (0) - не рубка.
        parts = np.zeros((30, 30), dtype=np.int64)
        parts[9:21, 9:21] = 2
        parts[10:20, 10:20] = 1
        out = ot.region_kinds(parts, [0, 1, 2],
                              [ot.BROADLEAF, ot.SOIL, ot.CONIFER], "forest")
        self.assertEqual(out[1], ot.SOIL)

    def test_inner_shares(self):
        parts = np.zeros((10, 10), dtype=np.int64)
        parts[0] = 1
        shares = ot.inner_shares(parts)
        self.assertEqual(shares[1], 0.0)
        self.assertAlmostEqual(shares[0], 80.0 / 90.0)

    def test_water_scenario_has_no_clearing(self):
        out = ot.region_kinds(self.parts, [0, 1, 1],
                              [ot.CONIFER, ot.SOIL], "water")
        self.assertEqual(out, [ot.OTHER, ot.OTHER, ot.OTHER])

    def test_ring_share(self):
        shares = ot.ring_shares(self.parts, [ot.CONIFER, ot.SOIL, ot.SOIL],
                                ot.CONIFER, [1, 2], 3)
        self.assertAlmostEqual(shares[1], 1.0)
        self.assertAlmostEqual(shares[2], 1.0)

    def test_clearing_behind_thin_rim(self):
        # Вырубка (1) в кольце смешанных пикселей «листвы» (2) шириной
        # в клетку, вокруг - хвоя (0). По одной границе рубки не видно.
        parts = np.zeros((30, 30), dtype=np.int64)
        parts[9:21, 9:21] = 2
        parts[10:20, 10:20] = 1
        out = ot.region_kinds(parts, [0, 1, 2],
                              [ot.CONIFER, ot.SOIL, ot.BROADLEAF], "forest")
        self.assertEqual(out[1], ot.CLEARING)

    def test_line_masks(self):
        masks = ot.line_masks(self.parts, [ot.CONIFER, ot.SOIL, ot.WATER])
        self.assertTrue(masks["roads"][4, 4])
        self.assertTrue(masks["water"][0, 15])
        self.assertFalse(masks["belts"].any())

    def test_classes_in_order(self):
        used, numbers = ot.classes_of([ot.WATER, ot.CONIFER, ot.WATER],
                                      "forest")
        self.assertEqual(used, [ot.CONIFER, ot.WATER])
        self.assertEqual(numbers.tolist(), [1, 0, 1])


if __name__ == "__main__":
    unittest.main()
