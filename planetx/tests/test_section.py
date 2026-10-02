# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Разрез вниз вдоль линии: точки по дуге, очаги в полосе, оболочки."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid as el  # noqa: E402
import quakes as qk  # noqa: E402
import section as sc  # noqa: E402


class TestSection(unittest.TestCase):

    def setUp(self):
        el.set_body(el.EARTH)

    def test_along_equator(self):
        distance, lats, lons = sc.along([(0.0, 0.0), (0.0, 10.0)], 11)
        self.assertTrue(np.allclose(lats, 0.0, atol=1e-9))
        self.assertTrue(np.allclose(lons, np.arange(11.0)))
        # 10° дуги - около 1112 км.
        self.assertAlmostEqual(float(distance[-1]), 1111.95, delta=2.0)
        self.assertIsNone(sc.along([(0.0, 0.0)]))

    def test_along_two_legs_even_step(self):
        distance, lats, lons = sc.along([(0.0, 0.0), (0.0, 5.0),
                                         (5.0, 5.0)], 101)
        step = np.diff(distance)
        self.assertTrue(np.allclose(step, step[0], rtol=1e-9))
        self.assertAlmostEqual(float(lats[50]), 0.0, places=6)
        self.assertAlmostEqual(float(lons[-1]), 5.0, places=6)

    def test_quakes_in_band(self):
        events = [qk.Quake(0.3, 5.0, 50.0, 6.0, None, "", ""),
                  qk.Quake(2.0, 5.0, 10.0, 5.0, None, "", ""),
                  qk.Quake(0.0, 20.0, 10.0, 5.0, None, "", "")]
        section = sc.build([(0.0, 0.0), (0.0, 10.0)], quakes=events,
                           width=100.0)
        self.assertEqual(len(section.quakes), 1)
        s, depth, mag, _ = section.quakes[0]
        self.assertAlmostEqual(s, 556.0, delta=5.0)
        self.assertEqual((depth, mag), (50.0, 6.0))

    def test_shells_cut_at_depth(self):
        section = sc.build([(0.0, 0.0), (0.0, 10.0)], depth=700.0)
        keys = [k for k, _, _, _ in sc.shells_below(section)]
        self.assertEqual(keys, ["upper_mantle", "transition_zone",
                                "lower_mantle"])
        last = sc.shells_below(section)[-1]
        self.assertEqual(last[2], 700.0)
        self.assertTrue(np.allclose(sc.moho(section), 24.4))


if __name__ == "__main__":
    unittest.main()
