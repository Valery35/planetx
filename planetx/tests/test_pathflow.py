# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/pathflow.py: поток по пути и его признак в KML."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid  # noqa: E402
import kml  # noqa: E402
import pathflow as pf  # noqa: E402

BEREZNIKI = (59.41, 56.80)
UST_LUGA = (59.68, 28.40)


class TestPath(unittest.TestCase):

    def setUp(self):
        ellipsoid.set_body(ellipsoid.EARTH)

    def test_length_is_great_circle(self):
        path = pf.Path([BEREZNIKI, UST_LUGA])
        a = np.radians(BEREZNIKI)
        b = np.radians(UST_LUGA)
        cos = (math.sin(a[0]) * math.sin(b[0])
               + math.cos(a[0]) * math.cos(b[0]) * math.cos(b[1] - a[1]))
        expected = math.acos(cos) * (2 * ellipsoid.A + ellipsoid.B) / 3
        self.assertAlmostEqual(path.length, expected, delta=1.0)
        self.assertGreater(len(path.units), 50)
        # Середина пути - на дуге большого круга, севернее обоих концов.
        lat, lon = path.at([path.length / 2.0])
        self.assertGreater(float(lat[0]), 60.0)

    def test_ends_and_clipping(self):
        path = pf.Path([BEREZNIKI, UST_LUGA])
        lat, lon = path.at([0.0, path.length, -5.0, path.length + 5.0])
        self.assertAlmostEqual(float(lat[0]), BEREZNIKI[0], places=6)
        self.assertAlmostEqual(float(lon[1]), UST_LUGA[1], places=6)
        self.assertAlmostEqual(float(lat[2]), BEREZNIKI[0], places=6)
        self.assertAlmostEqual(float(lon[3]), UST_LUGA[1], places=6)

    def test_one_point_is_refused(self):
        with self.assertRaises(ValueError):
            pf.Path([BEREZNIKI])


class TestDashes(unittest.TestCase):

    def setUp(self):
        ellipsoid.set_body(ellipsoid.EARTH)

    def test_ranges_step_and_inside(self):
        ranges = pf.dash_ranges(1000.0, 100.0, 0.25)
        self.assertTrue(np.all(ranges[:, 0] >= 0.0))
        self.assertTrue(np.all(ranges[:, 1] <= 1000.0))
        starts = ranges[1:-1, 0]
        self.assertTrue(np.allclose(np.diff(starts), 100.0))
        full = ranges[1:-1]
        self.assertTrue(np.allclose(full[:, 1] - full[:, 0],
                                    100.0 * pf.DASH_SHARE))

    def test_phase_moves_dashes_forward(self):
        # Поток идёт от первой точки к последней: с ростом сдвига начала
        # штрихов растут.
        a = pf.dash_ranges(1000.0, 100.0, 0.25)
        b = pf.dash_ranges(1000.0, 100.0, 0.30)
        self.assertAlmostEqual(float(b[2, 0] - a[2, 0]), 5.0, places=6)

    def test_spacing_follows_view_width(self):
        self.assertAlmostEqual(pf.spacing_for(1.0e6),
                               1.0e6 * pf.SPACING_SHARE)

    def test_near_keeps_dashes_at_view(self):
        path = pf.Path([BEREZNIKI, UST_LUGA])
        spacing = 2000.0
        lats, lons = pf.dashes(path, spacing, 0.0)
        near_lats, _ = pf.dashes(path, spacing, 0.0,
                                 near=(BEREZNIKI[0], BEREZNIKI[1], 0.5))
        self.assertGreater(len(lats), 500)
        self.assertLess(len(near_lats), 50)
        self.assertGreater(len(near_lats), 5)
        self.assertEqual(lats.shape[1], pf.PARTS + 1)

    def test_near_matches_full_check(self):
        # Отбор по вершинам пути даёт те же штрихи, что проверка середины
        # каждого штриха пути. Путь с поворотом, точки у пути, в стороне
        # и у изгиба, углы от малого до половины шара.
        path = pf.Path([BEREZNIKI, (55.75, 37.62), UST_LUGA, (69.0, 33.0)])
        spacing = 3000.0
        ranges = pf.dash_ranges(path.length, spacing, 0.37)
        middle = path.at(ranges.mean(axis=1))
        units = pf._unit(middle[0], middle[1])
        # Точка посреди отрезка пути: вершины дальше малого угла, штрихи
        # у неё находит только запас на длину отрезка.
        k = int(np.argmax(np.diff(path.cum)))
        mid = path.at([(path.cum[k] + path.cum[k + 1]) / 2.0])
        for lat, lon in (BEREZNIKI, (57.0, 45.0), (55.75, 37.62),
                         (62.0, 30.0), (40.0, 100.0),
                         (float(mid[0][0]), float(mid[1][0]))):
            for angle in (0.02, 0.05, 0.5, 3.0, 40.0, 179.0):
                cos = units @ pf._unit(lat, lon)
                full = ranges[cos >= math.cos(math.radians(angle))]
                fast = pf._near_ranges(path, ranges, lat, lon, angle)
                self.assertTrue(np.array_equal(full, fast),
                                (lat, lon, angle, len(full), len(fast)))

    def test_dash_color_is_lighter(self):
        r, g, b, a = pf.dash_color((200, 60, 20, 255))
        self.assertGreater(r, 200 / 255.0)
        self.assertGreater(b, 20 / 255.0)
        self.assertAlmostEqual(a, 1.0)


class TestKmlFlow(unittest.TestCase):

    def test_flow_survives_round_trip(self):
        place = kml.KPlace("Березники - Усть-Луга", "line",
                           [BEREZNIKI, UST_LUGA], flow=True)
        plain = kml.KPlace("Без потока", "line", [BEREZNIKI, UST_LUGA])
        text = kml.write_kml(kml.KFolder("Поток", children=[place, plain]))
        self.assertIn(kml.FLOW_DATA, text)
        back = kml.read_kml(text.encode("utf-8"))
        flows = {p.name: p.flow for p in back.children}
        self.assertEqual(flows, {"Березники - Усть-Луга": True,
                                 "Без потока": False})


if __name__ == "__main__":
    unittest.main()
