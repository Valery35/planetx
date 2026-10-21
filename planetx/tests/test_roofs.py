# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/roofs.py: крыши зданий для видимости и инсоляции."""
import math
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import ellipsoid  # noqa: E402
import roofs  # noqa: E402
import viewshed  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PERM = (14, 10751, 4933)
LAT, LON = 58.0, 56.0


def metres(dn, de):
    """Широта и долгота точки в dn, de метрах от LAT, LON."""
    lat = LAT + math.degrees(dn / ellipsoid.A)
    lon = LON + math.degrees(de / ellipsoid.A) / math.cos(math.radians(LAT))
    return lat, lon


def square(n0, e0, size):
    corners = [(n0, e0), (n0, e0 + size), (n0 + size, e0 + size),
               (n0 + size, e0)]
    return np.array([metres(n, e) for n, e in corners])


class TestBurn(unittest.TestCase):

    def test_building_with_courtyard(self):
        grid = roofs.Roofs(LAT, LON, 200.0, 2.0)
        grid.burn([square(0, 0, 60), square(20, 20, 20)], 25.0)
        at = grid.at(*np.array([metres(10, 10), metres(30, 30),
                                metres(-20, -20), metres(50, 50)]).T)
        self.assertEqual(at.tolist(), [25.0, 0.0, 0.0, 25.0])
        self.assertEqual(grid.count, 1)

    def test_taller_wins_and_outside_is_zero(self):
        grid = roofs.Roofs(LAT, LON, 100.0, 2.0)
        grid.burn([square(0, 0, 30)], 10.0)
        grid.burn([square(10, 10, 30)], 40.0)
        self.assertEqual(grid.at(*np.array([metres(15, 15)]).T)[0], 40.0)
        self.assertEqual(grid.at(*np.array([metres(5000, 0)]).T)[0], 0.0)

    def test_real_tile(self):
        lat, lon = 58.0105, 56.2294  # центр Перми, тайл PERM
        grid = roofs.Roofs(lat, lon, 1500.0, 2.0)
        path = os.path.join(DATA, "building_perm_{}_{}_{}.mvt".format(*PERM))
        with open(path, "rb") as f:
            grid.add_tile(PERM, f.read())
        self.assertGreater(grid.count, 100)
        self.assertGreater(float(grid.top.max()), 10.0)
        self.assertIn(PERM, roofs.tiles_around(lat, lon, 1500.0))


def cube(size):
    """Куб size метров треугольниками подряд, низ на нуле, ось Z вверх."""
    s = size / 2.0
    v = np.array([[x, y, z] for z in (0.0, size) for y in (-s, s)
                  for x in (-s, s)])
    faces = [(0, 1, 3), (0, 3, 2), (4, 5, 7), (4, 7, 6), (0, 1, 5),
             (0, 5, 4), (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4),
             (1, 3, 7), (1, 7, 5)]
    return v[np.array(faces).ravel()]


class TestOwn(unittest.TestCase):

    def test_model_rotation_matches_models(self):
        import models
        for angles in ((0, 0, 0), (37, 10, -5), (200, 0, 90)):
            self.assertTrue(np.allclose(roofs._rotation(*angles),
                                        models.rotation(*angles)))

    def test_model_cube_on_ground(self):
        grid = roofs.Roofs(LAT, LON, 100.0, 1.0)
        lats, lons, tops = roofs.model_triangles(
            cube(20.0), LAT, LON, 45.0, 0.0, 0.0, (1.0, 1.0, 1.0), 3.0)
        grid.burn_triangles(lats, lons, tops)
        inside = grid.at(*np.array([metres(0, 0), metres(5, 5)]).T)
        outside = grid.at(*np.array([metres(0, 15)]).T)
        # Куб на подъёме 3 м: крыша 23 м, угол повёрнутого куба - снаружи
        # квадрата 20 м по оси.
        self.assertEqual(inside.tolist(), [23.0, 23.0])
        self.assertEqual(outside.tolist(), [0.0])

    def test_footprint_of_extruded_layer(self):
        import buildings
        path = os.path.join(DATA, "building_perm_{}_{}_{}.mvt".format(*PERM))
        with open(path, "rb") as f:
            fp = buildings.footprints(PERM, f.read())
        lat, lon = fp.latlon.mean(axis=0)
        grid = roofs.Roofs(lat, lon, 1500.0, 2.0)
        grid.burn_footprint(fp)
        self.assertGreater(grid.count, 100)
        self.assertAlmostEqual(float(grid.top.max()), float(fp.height.max()),
                               places=3)


class TestViewshed(unittest.TestCase):

    def test_wall_hides_ground_behind(self):
        grid = roofs.Roofs(LAT, LON, 600.0, 2.0)
        # Стена 30 м на севере между наблюдателем и землёй за ней.
        grid.burn([square(100, -10, 20)], 30.0)

        def flat(lats, lons):
            return np.zeros(np.shape(lats))

        def built(lats, lons):
            return flat(lats, lons) + grid.at(lats, lons)

        north = np.array([metres(300, 0)]).T
        bare = viewshed.compute(LAT, LON, 500.0, 2.0, flat)
        walled = viewshed.compute(LAT, LON, 500.0, 2.0, built)
        self.assertTrue(bare.at(*north, ellipsoid.A)[0][0])
        self.assertFalse(walled.at(*north, ellipsoid.A)[0][0])


if __name__ == "__main__":
    unittest.main()
