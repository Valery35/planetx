# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Границы литосферных плит PB2002: файл данных, окно вида, щелчок."""
import math
import os
import sys
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import plates  # noqa: E402

DATA = os.path.join(os.path.dirname(CORE), "data", "plates.json")


def load():
    with open(DATA, encoding="utf-8") as fh:
        return plates.Plates.from_text(fh.read())


class TestData(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.p = load()

    def test_counts_and_classes(self):
        self.assertEqual(len(self.p.plates), 54)
        self.assertGreater(len(self.p.boundaries), 1500)
        codes = {b.code for b in self.p.boundaries}
        self.assertEqual(codes, set(plates.GROUP))
        self.assertTrue(all(b.speed >= 0.0 for b in self.p.boundaries))
        names = {pl.name for pl in self.p.plates}
        self.assertIn("Pacific", names)
        self.assertIn("Eurasia", names)

    def test_steps_short_and_not_across_dateline(self):
        worst = 0.0
        for b in self.p.boundaries:
            for i in range(len(b.lats) - 1):
                self.assertLess(abs(b.lons[i + 1] - b.lons[i]), 180.0)
                worst = max(worst, plates._angle(
                    b.lats[i], b.lons[i], b.lats[i + 1], b.lons[i + 1]))
        # Запас nearest держится на длине шага.
        self.assertLess(worst, plates.STEP_MAX)

    def test_japan_trench_is_subduction(self):
        # Японский жёлоб у эпицентра Тохоку: граница плит рядом,
        # схождение.
        found = plates.nearest(self.p, 38.3, 143.9, 80000.0)
        self.assertIsNotNone(found)
        self.assertEqual(plates.group(found.code), "convergent")

    def test_far_from_boundaries(self):
        # Середина Африки - до границ сотни километров.
        self.assertIsNone(plates.nearest(self.p, 5.0, 20.0, 50000.0))


class TestHelpers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.p = load()

    def test_in_view(self):
        b = self.p.boundaries[0]
        self.assertTrue(plates.in_view(b, b.lats[0], b.lons[0], 0.001))
        self.assertTrue(plates.in_view(b, -b.lats[0], b.lons[0] + 180.0,
                                       math.pi))

    def test_colors_by_group(self):
        self.assertEqual(plates.color("SUB"), plates.COLORS["convergent"])
        self.assertEqual(plates.color("OSR"), plates.COLORS["divergent"])
        self.assertEqual(plates.color("OTF"), plates.COLORS["transform"])


if __name__ == "__main__":
    unittest.main()
