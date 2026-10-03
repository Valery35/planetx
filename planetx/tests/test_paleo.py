# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Палеогеография: адрес запроса, разбор ответа, периоды."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import paleo  # noqa: E402

SQUARE = [[10.0, 0.0], [20.0, 0.0], [20.0, 5.0], [10.0, 5.0], [10.0, 0.0]]


class TestPaleo(unittest.TestCase):

    def test_url(self):
        self.assertEqual(
            paleo.url(250),
            "https://gws.gplates.org/reconstruct/coastlines/"
            "?time=250&model=MERDITH2021")

    def test_period(self):
        self.assertEqual(paleo.period(0), "quaternary")
        self.assertEqual(paleo.period(100), "cretaceous")
        self.assertEqual(paleo.period(280), "permian")
        self.assertEqual(paleo.period(600), "precambrian")

    def test_parse_polygon(self):
        data = {"features": [{"geometry": {"type": "Polygon",
                                           "coordinates": [SQUARE]}}]}
        rings = paleo.parse(data)
        # Широта первой, замыкающая точка убрана.
        self.assertEqual(rings, [[(0.0, 10.0), (0.0, 20.0), (5.0, 20.0),
                                  (5.0, 10.0)]])

    def test_parse_multipolygon_and_small(self):
        small = [[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.0]]
        data = {"features": [{"geometry": {
            "type": "MultiPolygon",
            "coordinates": [[SQUARE], [small]]}}]}
        self.assertEqual(len(paleo.parse(data)), 1)

    def test_largest_rings_kept(self):
        big = [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 0.0]]
        data = {"features": [
            {"geometry": {"type": "Polygon", "coordinates": [SQUARE]}},
            {"geometry": {"type": "Polygon", "coordinates": [big]}}]}
        rings = paleo.parse(data, count=1)
        self.assertEqual(len(rings), 1)
        self.assertEqual(rings[0][1], (0.0, 40.0))

    def test_parse_empty(self):
        self.assertEqual(paleo.parse(None), [])
        self.assertEqual(paleo.parse({"features": [{"geometry": None}]}), [])

    def test_thin(self):
        ring = [(float(i), 0.0) for i in range(1000)]
        thinned = paleo.thin(ring, 100)
        self.assertEqual(len(thinned), 100)
        self.assertEqual(thinned[0], ring[0])

    def test_unwrapped_plain_ring(self):
        ring = [(0.0, 10.0), (0.0, 20.0), (5.0, 20.0)]
        self.assertEqual(paleo.unwrapped(ring), ring)

    def test_unwrapped_across_180(self):
        ring = [(0.0, 170.0), (0.0, -170.0), (5.0, -170.0), (5.0, 170.0)]
        lons = [p[1] for p in paleo.unwrapped(ring)]
        self.assertEqual(lons, [170.0, 190.0, 190.0, 170.0])

    def test_unwrapped_around_pole(self):
        ring = [(-80.0, float(lon)) for lon in range(-180, 180, 30)]
        points = paleo.unwrapped(ring)
        # Контур обошёл полюс: дополнен до южного полюса.
        self.assertEqual(points[-2:], [(-90.0, 180.0), (-90.0, -180.0)])
        self.assertEqual(points[-3], (-80.0, 180.0))

    def test_shapes_are_closed_lines(self):
        shape = paleo.shapes([[(0.0, 0.0), (0.0, 1.0), (1.0, 1.0)]])[0]
        self.assertEqual(shape.kind, "line")
        self.assertEqual(shape.points[0], shape.points[-1])


if __name__ == "__main__":
    unittest.main()
