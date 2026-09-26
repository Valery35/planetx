# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Перелёт по методу van Wijk и Nuij."""
import math
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import camera as cm  # noqa: E402
import flight as fl  # noqa: E402
import navigation as nav  # noqa: E402

PERM = (58.0105, 56.2294)
MOSCOW = (55.7558, 37.6173)
SCALE = 2.0 * math.tan(math.radians(22.5))

CASES = (
    ("Москва - Пермь на 3 км", 1.15e6, 3000 * SCALE, 3000 * SCALE),
    ("космос - улица", 0.0, 2e7 * SCALE, 300 * SCALE),
    ("улица - улица через полпланеты", 1.9e7, 300 * SCALE, 300 * SCALE),
    ("улица - космос рядом", 5e4, 300 * SCALE, 1e7 * SCALE),
    ("соседний дом", 150.0, 500 * SCALE, 500 * SCALE),
)


def metric_steps(path, count=2000):
    """Приращения ds по равным шагам s, в метрике статьи.

    ds² = (ρ²·du² + dw²/ρ²) / w². Из формул пути du/ds = w·sech/ρ
    и dw/ds = -ρ·w·tanh, и тогда ds'² = sech² + tanh² = 1.
    """
    s = np.linspace(0.0, path.length, count + 1)
    uw = np.array([path.at(x) for x in s])
    du, dw = np.diff(uw[:, 0]), np.diff(uw[:, 1])
    w = np.sqrt(uw[1:, 1] * uw[:-1, 1])
    rho = fl.RHO
    return np.sqrt(rho * rho * du * du + dw * dw / (rho * rho)) / w


class TestPath(unittest.TestCase):

    def test_ends(self):
        for name, u1, w0, w1 in CASES:
            path = fl.Path(u1, w0, w1)
            u, w = path.at(0.0)
            self.assertAlmostEqual(u, 0.0, delta=1e-6 * max(u1, 1), msg=name)
            self.assertAlmostEqual(w, w0, delta=1e-9 * w0, msg=name)
            u, w = path.at(path.length)
            target_u = 0.0 if path.zoom_only else u1
            self.assertAlmostEqual(u, target_u, delta=1e-6 * max(u1, 1.0),
                                   msg=name)
            self.assertAlmostEqual(w, w1, delta=1e-6 * w1, msg=name)

    def test_pure_zoom_length(self):
        path = fl.Path(0.0, 2e7 * SCALE, 300 * SCALE)
        self.assertTrue(path.zoom_only)
        self.assertAlmostEqual(path.length,
                               abs(math.log(300 / 2e7)) / fl.RHO, places=12)

    def test_constant_speed_in_the_metric(self):
        for name, u1, w0, w1 in CASES:
            path = fl.Path(u1, w0, w1)
            steps = metric_steps(path)
            mean = steps.mean()
            self.assertLess(np.abs(steps / mean - 1.0).max(), 0.01, name)
            self.assertAlmostEqual(steps.sum(), path.length,
                                   delta=0.01 * path.length, msg=name)

    def test_long_flight_rises(self):
        path = fl.Path(1.15e6, 3000 * SCALE, 3000 * SCALE)
        top = max(path.at(s)[1] for s in np.linspace(0, path.length, 200))
        self.assertGreater(top, 50 * 3000 * SCALE)

    def test_no_nan(self):
        for name, u1, w0, w1 in CASES:
            path = fl.Path(u1, w0, w1)
            for s in np.linspace(0, path.length, 50):
                u, w = path.at(s)
                self.assertTrue(math.isfinite(u) and math.isfinite(w), name)
                self.assertGreater(w, 0.0, name)


class TestFlight(unittest.TestCase):

    def flight(self):
        start = nav.Pose(*MOSCOW, 3000.0, heading=120.0, tilt=45.0)
        return fl.Flight(start, *PERM, 2000.0)

    def test_starts_and_ends_exactly(self):
        f = self.flight()
        p = f.pose_at(0.0)
        self.assertAlmostEqual(p.lat, MOSCOW[0], places=9)
        self.assertAlmostEqual(p.lon, MOSCOW[1], places=9)
        self.assertAlmostEqual(p.distance, 3000.0, delta=1e-6)
        self.assertAlmostEqual(p.heading, 120.0, places=9)
        p = f.pose_at(f.duration)
        self.assertEqual((p.lat, p.lon, p.distance, p.heading, p.tilt),
                         (PERM[0], PERM[1], 2000.0, 0.0, 0.0))

    def test_no_jump_before_the_end(self):
        f = self.flight()
        p = f.pose_at(f.duration * 0.999999)
        self.assertLess(abs(p.lat - PERM[0]) + abs(p.lon - PERM[1]), 1e-4)
        self.assertAlmostEqual(p.distance, 2000.0, delta=1.0)

    def test_time_runs_evenly_along_the_path(self):
        f = self.flight()
        for share in (0.1, 0.25, 0.5, 0.9):
            self.assertAlmostEqual(f.s_at(share * f.duration),
                                   share * f.path.length, places=9)

    def test_duration(self):
        f = self.flight()
        self.assertAlmostEqual(f.duration, f.path.length / fl.SPEED)
        self.assertTrue(3.0 < f.duration < 6.0, f.duration)
        near = fl.Flight(nav.Pose(*PERM, 1000.0), PERM[0] + 1e-5, PERM[1],
                         1000.0)
        self.assertEqual(near.duration, fl.MIN_TIME)

    def test_heading_takes_short_way(self):
        f = fl.Flight(nav.Pose(*PERM, 1000.0, heading=350.0), *MOSCOW,
                      1000.0, heading=10.0)
        mid = f.pose_at(f.duration / 2).heading
        self.assertTrue(mid > 355.0 or mid < 5.0, mid)

    def test_across_the_antimeridian(self):
        f = fl.Flight(nav.Pose(60.0, 170.0, 5000.0), 60.0, -170.0, 5000.0)
        for t in np.linspace(0, f.duration, 20):
            lon = f.pose_at(t).lon
            self.assertTrue(lon >= 170.0 or lon <= -170.0, lon)


class TestNavigatorFlight(unittest.TestCase):

    def test_flight_runs_and_press_stops_it(self):
        cam = cm.Camera(np.zeros(3), np.eye(3), width=1920, height=1080)
        n = nav.Navigator(cam, nav.Pose(*MOSCOW, 3000.0))
        f = fl.Flight(n.pose, *PERM, 2000.0)
        n.start_flight(f, 0.0)
        self.assertTrue(n.step(1.0))
        self.assertNotEqual((n.pose.lat, n.pose.lon), MOSCOW)
        n.press(960, 540, 1.1)
        self.assertIsNone(n.flight)

    def test_flight_ends_at_target(self):
        cam = cm.Camera(np.zeros(3), np.eye(3), width=1920, height=1080)
        n = nav.Navigator(cam, nav.Pose(*MOSCOW, 3000.0))
        f = fl.Flight(n.pose, *PERM, 2000.0)
        n.start_flight(f, 0.0)
        t = 0.0
        while n.step(t):
            t += 1 / 60
        self.assertEqual((n.pose.lat, n.pose.lon), PERM)


class TestParse(unittest.TestCase):

    def test_formats(self):
        for text in ("58.0105, 56.2294", "58.0105 56.2294",
                     " 58.0105,56.2294 ", "58,0105; 56,2294"):
            self.assertEqual(fl.parse_latlon(text), PERM, text)

    def test_rejects(self):
        for text in ("", "58.0105", "91, 10", "10, 181", "север, юг",
                     "1, 2, 3"):
            self.assertIsNone(fl.parse_latlon(text), text)


if __name__ == "__main__":
    unittest.main()
