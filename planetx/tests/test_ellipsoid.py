# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Эллипсоид WGS84, пересчёт в ECEF и пересечение луча."""
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import ellipsoid as el  # noqa: E402

MM = 1e-3

# Эталон - PROJ из QGIS 4.0.3, EPSG:4979 в EPSG:4978, 26 сентября 2026.
PROJ = (
    (58.0105, 56.2294, 150.0,
     (1882812.758132668, 2815636.425723567, 5386484.577109812)),
    (-89.9, 10.0, 0.0,
     (10999.70400604673, 1939.5445960730267, -6356742.567109314)),
    (0.0, 0.0, 20000000.0, (26378137.0, 0.0, 0.0)),
    (45.0, -120.0, -400.0,
     (-2258654.0180682275, -3912103.516013765, 4487065.566153445)),
)

PERM = (58.0105, 56.2294)


def random_points(count, seed=1):
    rng = np.random.default_rng(seed)
    lat = np.degrees(np.arcsin(rng.uniform(-1.0, 1.0, count)))
    lon = rng.uniform(-180.0, 180.0, count)
    h = rng.uniform(-11000.0, 40e6, count)
    # Особые точки - полюса, экватор, линия смены дат.
    lat[:6] = [90.0, -90.0, 0.0, 0.0, 89.999999, -45.0]
    lon[:6] = [0.0, 123.0, 180.0, -180.0, 17.0, 0.0]
    h[:6] = [0.0, 0.0, 0.0, 1e7, 5.0, -11000.0]
    return lat, lon, h


class TestGeodeticToEcef(unittest.TestCase):

    def test_matches_proj(self):
        for lat, lon, h, expected in PROJ:
            got = el.geodetic_to_ecef(lat, lon, h)
            self.assertLess(np.abs(got - expected).max(), MM,
                            (lat, lon, h))

    def test_shape_follows_input(self):
        self.assertEqual(el.geodetic_to_ecef(0.0, 0.0).shape, (3,))
        grid = el.geodetic_to_ecef(np.zeros((4, 5)), np.zeros((4, 5)))
        self.assertEqual(grid.shape, (4, 5, 3))

    def test_poles_and_equator(self):
        north = el.geodetic_to_ecef(90.0, 0.0)
        self.assertAlmostEqual(north[2], el.B, delta=MM)
        east = el.geodetic_to_ecef(0.0, 90.0)
        self.assertAlmostEqual(east[1], el.A, delta=MM)


class TestRoundTrip(unittest.TestCase):

    def test_round_trip_under_one_millimetre(self):
        lat, lon, h = random_points(200000)
        xyz = el.geodetic_to_ecef(lat, lon, h)
        lat2, lon2, h2 = el.ecef_to_geodetic(xyz)
        back = el.geodetic_to_ecef(lat2, lon2, h2)
        error = np.sqrt(((back - xyz) ** 2).sum(axis=1))
        self.assertLess(error.max(), MM)
        self.assertLess(np.abs(h2 - h).max(), MM)

    def test_latitude_and_height_recovered(self):
        lat, lon, h = random_points(20000, seed=2)
        lat2, _, h2 = el.ecef_to_geodetic(el.geodetic_to_ecef(lat, lon, h))
        # Угол 1e-8 градуса на поверхности - около 1 мм.
        self.assertLess(np.abs(lat2 - lat).max(), 1e-8)
        self.assertLess(np.abs(h2 - h).max(), MM)

    def test_matches_proj_backwards(self):
        for lat, lon, h, xyz in PROJ:
            lat2, lon2, h2 = el.ecef_to_geodetic(np.array(xyz))
            self.assertAlmostEqual(float(lat2), lat, delta=1e-8)
            self.assertAlmostEqual(float(h2), h, delta=MM)
            if abs(lat) < 90.0:
                self.assertAlmostEqual(float(lon2), lon, delta=1e-8)


class TestNormal(unittest.TestCase):

    def test_normal_is_unit_and_perpendicular_to_surface(self):
        lat, lon, _ = random_points(1000, seed=3)
        lat = np.clip(lat, -89.9, 89.9)
        n = el.surface_normal(lat, lon)
        self.assertLess(np.abs(np.linalg.norm(n, axis=1) - 1.0).max(), 1e-12)
        step = 1e-6
        d_lat = (el.geodetic_to_ecef(lat + step, lon)
                 - el.geodetic_to_ecef(lat - step, lon))
        d_lon = (el.geodetic_to_ecef(lat, lon + step)
                 - el.geodetic_to_ecef(lat, lon - step))
        for d in (d_lat, d_lon):
            d = d / np.linalg.norm(d, axis=1)[:, None]
            self.assertLess(np.abs((n * d).sum(axis=1)).max(), 1e-6)


class TestRay(unittest.TestCase):

    def test_straight_down_from_100_m_over_perm(self):
        target = el.geodetic_to_ecef(*PERM)
        normal = el.surface_normal(*PERM)
        eye = el.geodetic_to_ecef(*PERM, 100.0)
        t = el.ray_intersect(eye, -normal)
        self.assertAlmostEqual(t, 100.0, delta=MM)
        hit = eye - normal * t
        self.assertLess(np.linalg.norm(hit - target), MM)

    def test_from_space_toward_centre(self):
        eye = np.array([el.A + 20e6, 0.0, 0.0])
        self.assertAlmostEqual(el.ray_intersect(eye, [-1.0, 0.0, 0.0]),
                               20e6, delta=MM)

    def test_direction_need_not_be_unit(self):
        eye = np.array([el.A + 1000.0, 0.0, 0.0])
        self.assertAlmostEqual(el.ray_intersect(eye, [-10.0, 0.0, 0.0]),
                               100.0, delta=1e-6)

    def test_miss_and_behind(self):
        eye = np.array([el.A + 1000.0, 0.0, 0.0])
        self.assertIsNone(el.ray_intersect(eye, [0.0, 0.0, 1.0]))
        self.assertIsNone(el.ray_intersect(eye, [1.0, 0.0, 0.0]))

    def test_grazing_ray_near_horizon(self):
        # Сечение по экватору - окружность радиуса A. Луч под углом beta
        # к направлению на центр встречает её на расстоянии
        # r cos(beta) - sqrt(A^2 - r^2 sin^2(beta)).
        r = el.A + 1000.0
        eye = np.array([r, 0.0, 0.0])
        tangent = np.arcsin(el.A / r)
        for beta in (tangent - 1e-4, tangent - 1e-7):
            d = np.array([-np.cos(beta), np.sin(beta), 0.0])
            expected = r * np.cos(beta) - np.sqrt(
                el.A ** 2 - (r * np.sin(beta)) ** 2)
            self.assertAlmostEqual(el.ray_intersect(eye, d), expected,
                                   delta=MM)
        above = tangent + 1e-7
        d = np.array([-np.cos(above), np.sin(above), 0.0])
        self.assertIsNone(el.ray_intersect(eye, d))

    def test_inflated_ellipsoid(self):
        eye = el.geodetic_to_ecef(*PERM, 1000.0)
        normal = el.surface_normal(*PERM)
        t = el.ray_intersect(eye, -normal, h=300.0)
        _, _, h = el.ecef_to_geodetic(eye - normal * t)
        # Раздутый эллипсоид отличается от поверхности на высоте 300 м
        # на доли метра.
        self.assertAlmostEqual(float(h), 300.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
