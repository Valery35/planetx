# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Землетрясения: разбор сводки USGS, цвета, точки."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid as el  # noqa: E402
import quakes as qk  # noqa: E402

FEED = {"type": "FeatureCollection", "features": [
    {"type": "Feature",
     "properties": {"mag": 6.1, "place": "Kuril Islands",
                    "time": 1790000000000, "url": "https://x/1"},
     "geometry": {"type": "Point", "coordinates": [150.0, 45.0, 35.0]}},
    {"type": "Feature", "properties": {"mag": None},
     "geometry": {"type": "Point", "coordinates": [1.0, 2.0, 3.0]}},
    {"type": "Feature", "properties": {"mag": 4.7},
     "geometry": {"type": "Point", "coordinates": [140.0, 30.0]}},
    {"type": "Feature", "properties": {"mag": 5.0, "time": None},
     "geometry": {"type": "Point", "coordinates": [-70.0, -20.0, 600.0]}},
]}


class TestQuakes(unittest.TestCase):

    def setUp(self):
        el.set_body(el.EARTH)

    def test_parse_skips_incomplete(self):
        got = qk.parse(FEED)
        self.assertEqual(len(got), 2)
        self.assertEqual((got[0].lat, got[0].lon, got[0].depth),
                         (45.0, 150.0, 35.0))
        self.assertEqual(got[0].time, 1790000000.0)
        self.assertIsNone(got[1].time)
        self.assertEqual(qk.parse(None), [])

    def test_colors_and_sizes(self):
        colors = qk.depth_colors([0.0, 700.0, 900.0])
        self.assertEqual(colors[0].tolist(), [230, 40, 30])
        self.assertEqual(colors[1].tolist(), colors[2].tolist())
        self.assertEqual(qk.sizes([4.5, 6.5, 11.0]).tolist(),
                         [4.0, 10.0, 22.0])

    def test_focus_below_epicenter(self):
        events = qk.parse(FEED)

        def ground(lat, lon):
            return np.full(len(lat), 100.0)
        focus, epi = qk.points(events, 2.0, ground)
        _, _, hf = el.ecef_to_geodetic(focus)
        _, _, he = el.ecef_to_geodetic(epi)
        # Масштаб 2: очаг на 35 км - на -70 км, рельеф 100 м - 200 м.
        self.assertAlmostEqual(float(hf[0]), -70000.0, delta=0.1)
        self.assertAlmostEqual(float(he[0]), 200.0, delta=0.1)

    def test_facing_hides_far_side(self):
        events = qk.parse(FEED)
        _, epi = qk.points(events, 1.0, lambda la, lo: np.zeros(len(la)))
        eye = el.geodetic_to_ecef(45.0, 150.0, 2.0e7)
        lats = [q.lat for q in events]
        lons = [q.lon for q in events]
        self.assertEqual(qk.facing(eye, epi, lats, lons).tolist(),
                         [True, False])


class TestTime(unittest.TestCase):

    def test_window_keeps_events_without_time(self):
        seconds = [100.0, 200.0, float("nan"), 300.0]
        got = qk.in_window(seconds, (150.0, 250.0))
        self.assertEqual(got.tolist(), [False, True, True, False])
        self.assertEqual(qk.in_window(seconds, None).tolist(), [True] * 4)

    def test_span_ignores_missing_time(self):
        events = qk.parse(FEED)
        self.assertEqual(qk.span(events), (1790000000.0, 1790000000.0))
        self.assertIsNone(qk.span(events[1:]))


if __name__ == "__main__":
    unittest.main()
