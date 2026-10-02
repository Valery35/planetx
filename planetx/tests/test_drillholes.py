# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Скважины: ствол по минимальной кривизне, разбор таблиц."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import drillholes as dh  # noqa: E402


class TestAxis(unittest.TestCase):

    def test_vertical_without_survey(self):
        nodes = dh.axis(150.0, 80.0)
        self.assertEqual(nodes[-1].tolist(), [80.0, 0.0, 0.0, 70.0])

    def test_straight_inclined(self):
        # Зенит 30°, азимут 90° (восток), 100 м по стволу.
        nodes = dh.axis(0.0, 100.0, [(0.0, 30.0, 90.0), (100.0, 30.0, 90.0)])
        md, east, north, z = nodes[-1]
        self.assertAlmostEqual(east, 50.0, places=6)
        self.assertAlmostEqual(north, 0.0, places=6)
        self.assertAlmostEqual(z, -100.0 * math.cos(math.radians(30.0)),
                               places=6)

    def test_arc_of_constant_curvature(self):
        # Набор зенита от 0 до 90° на дуге радиуса 100 м к северу:
        # забой на 100 м к северу и на 100 м ниже устья. Минимальная
        # кривизна на дуге точна.
        length = 100.0 * math.pi / 2.0
        nodes = dh.axis(0.0, length, [(0.0, 0.0, 0.0), (length, 90.0, 0.0)])
        _, east, north, z = nodes[-1]
        self.assertAlmostEqual(north, 100.0, places=6)
        self.assertAlmostEqual(z, -100.0, places=6)
        self.assertAlmostEqual(east, 0.0, places=6)
        # Середина дуги лежит на окружности, а не на хорде.
        mid = dh.point_at(nodes, length / 2.0)
        radius = math.hypot(mid[1] - 100.0, mid[2] - 0.0)
        self.assertAlmostEqual(radius, 100.0, delta=0.05)

    def test_extends_below_last_station(self):
        nodes = dh.axis(0.0, 200.0, [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)])
        self.assertAlmostEqual(nodes[-1][3], -200.0)

    def test_piece_has_ends(self):
        nodes = dh.axis(0.0, 100.0)
        part = dh.piece(nodes, 20.0, 35.0)
        self.assertEqual(part[0].tolist(), [0.0, 0.0, -20.0])
        self.assertEqual(part[-1].tolist(), [0.0, 0.0, -35.0])


class TestZenith(unittest.TestCase):

    def test_conventions(self):
        self.assertEqual(dh.zeniths([-90.0, -60.0], "dip").tolist(),
                         [0.0, 30.0])
        self.assertEqual(dh.zeniths([90.0, 60.0], "DIP").tolist(),
                         [0.0, 30.0])
        self.assertEqual(dh.zeniths([0.0, 10.0], "inc").tolist(),
                         [0.0, 10.0])
        self.assertEqual(dh.zeniths([2.0, 5.0], "dip").tolist(), [2.0, 5.0])


class TestAssemble(unittest.TestCase):

    def test_synonyms_swapped_and_orphans(self):
        collars = [{"BHID": "A", "ELEV": 120.0, "TD": 50.0, "x": 1, "y": 2},
                   {"BHID": 7.0, "ELEV": 100.0, "TD": None, "x": 3, "y": 4}]
        intervals = [{"bhid": "A", "from_m": 10.0, "to_m": 0.0, "lith": "Q"},
                     {"bhid": "A", "from_m": 10.0, "to_m": 30.0,
                      "lith": "ПЦТ", "grade": 5},
                     {"bhid": 7, "from_m": 0.0, "to_m": 60.0, "lith": "Q"},
                     {"bhid": "Z", "from_m": 0.0, "to_m": 5.0, "lith": "Q"}]
        surveys = [{"hole": "A", "depth": 0.0, "azimuth": 90.0,
                    "dip": -60.0}]
        holes, skipped = dh.assemble(collars, intervals, surveys)
        self.assertEqual([h.hole_id for h in holes], ["A", "7"])
        a, seven = holes
        self.assertEqual([(i.start, i.end, i.code) for i in a.intervals],
                         [(0.0, 10.0, "Q"), (10.0, 30.0, "ПЦТ")])
        self.assertEqual(a.intervals[1].extra, {"grade": 5})
        # Забоя нет - он по нижнему интервалу.
        self.assertEqual(seven.eoh, 60.0)
        # dip -60 - зенит 30, на восток.
        self.assertAlmostEqual(a.axis[-1][1], 50.0 * 0.5, places=6)
        self.assertEqual(skipped, {"interval_swapped": 1,
                                   "interval_no_collar": 1})

    def test_code_color_is_stable(self):
        self.assertEqual(dh.code_color("КрII"), dh.code_color("КрII"))
        self.assertEqual(dh.code_color("Q", {"Q": "#ff0080"}), (255, 0, 128))


if __name__ == "__main__":
    unittest.main()
