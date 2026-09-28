# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Навигация: захват Земли, колесо, наклон, инерция."""
import math
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import camera as cm  # noqa: E402
import navigation as nav  # noqa: E402

PERM = (58.0105, 56.2294)
W, H = 1920, 1080
ROLL = 1e-12


def navigator(distance, heading=0.0, tilt=0.0, where=PERM):
    cam = cm.Camera(np.zeros(3), np.eye(3), width=W, height=H)
    return nav.Navigator(cam, nav.Pose(*where, distance, heading, tilt))


def on_earth(cam, rng):
    """Случайный пиксель, под которым есть Земля."""
    while True:
        px, py = rng.uniform(0.1, 0.9, 2) * [W, H]
        if nav.ground_under(cam, px, py) is not None:
            return px, py


def pixel(cam, point):
    return nav.pixel_at(cam, cam.eye, cam.rotation, point)


def near_limb(cam, px, py, share=0.85):
    """Пиксель дальше share радиуса диска Земли от его середины.

    Середина диска - проекция центра Земли, радиус меряется лучами
    в сторону пикселя.
    """
    centre = pixel(cam, np.zeros(3))
    if centre is None:
        return False
    offset = np.array([px, py]) - centre
    dist = float(np.linalg.norm(offset))
    if dist == 0.0:
        return False
    u = offset / dist
    inside, outside = 0.0, 4.0 * max(W, H)
    if nav.ground_under(cam, *(centre + u * outside)) is not None:
        return False
    for _ in range(20):
        mid = 0.5 * (inside + outside)
        if nav.ground_under(cam, *(centre + u * mid)) is not None:
            inside = mid
        else:
            outside = mid
    return dist > share * inside


class TestGrab(unittest.TestCase):

    def check_drags(self, n, count, reach, seed):
        rng = np.random.default_rng(seed)
        cam = n.camera
        heading, tilt, distance = n.pose.heading, n.pose.tilt, \
            n.pose.distance
        moved = 0
        t = 0.0
        for _ in range(count):
            px, py = on_earth(cam, rng)
            self.assertTrue(n.press(px, py, t))
            point = n.grab
            for _ in range(3):
                t += 0.016
                qx = min(max(px + rng.uniform(-reach, reach), 1), W - 1)
                qy = min(max(py + rng.uniform(-reach, reach), 1), H - 1)
                if nav.ground_under(cam, qx, qy) is None:
                    # За краем диска точку поставить некуда.
                    self.assertFalse(n.drag(qx, qy, t))
                    continue
                if near_limb(cam, qx, qy):
                    # У края диска часть направлений недостижима, когда
                    # круг до точки захвата накрывает полюс: север
                    # в точке взгляда закреплён вверху окна.
                    if not n.drag(qx, qy, t):
                        continue
                else:
                    self.assertTrue(n.drag(qx, qy, t), (qx, qy))
                moved += 1
                self.assertLess(np.linalg.norm(pixel(cam, point)
                                               - [qx, qy]), 0.5)
                self.assertLess(abs(nav.roll(cam, n.pose)), ROLL)
            n.release(t + 1.0)
        # Захват не трогает азимут, наклон и расстояние.
        self.assertEqual((n.pose.heading, n.pose.tilt, n.pose.distance),
                         (heading, tilt, distance))
        return moved

    def test_street_level(self):
        self.assertGreater(self.check_drags(navigator(500.0), 34, 200, 1),
                           95)

    def test_tilted(self):
        n = navigator(2000.0, 40.0, 60.0)
        self.assertGreater(self.check_drags(n, 33, 150, 2), 90)

    def test_from_space(self):
        n = navigator(2.0e7)
        self.assertGreater(self.check_drags(n, 33, 150, 3), 50)

    def test_straight_down_keeps_heading(self):
        n = navigator(3000.0, 70.0, 0.0)
        n.press(W / 2, H / 2, 0.0)
        n.drag(W / 2 + 300, H / 2 - 200, 0.02)
        self.assertEqual(n.pose.heading, 70.0)

    def test_press_off_the_globe(self):
        n = navigator(2.0e7)
        self.assertFalse(n.press(5, 5, 0.0))
        self.assertFalse(n.drag(50, 50, 0.1))

    def test_impossible_drag_leaves_camera(self):
        # Точку у центра нельзя увести за край диска Земли.
        n = navigator(2.0e7)
        n.press(W / 2, H / 2, 0.0)
        eye = n.camera.eye.copy()
        self.assertFalse(n.drag(3, 3, 0.1))
        self.assertTrue(np.array_equal(n.camera.eye, eye))


class TestWheel(unittest.TestCase):

    def test_point_under_cursor_stays(self):
        rng = np.random.default_rng(4)
        for distance, tilt in ((2.0e7, 0.0), (5000.0, 0.0),
                               (3000.0, 60.0)):
            n = navigator(distance, 20.0, tilt)
            cam = n.camera
            for _ in range(10):
                px, py = on_earth(cam, rng)
                point = nav.ground_under(cam, px, py)
                d0 = n.pose.distance
                pose = nav.zoom(cam, n.pose, px, py, 0.8)
                self.assertIsNotNone(pose, (distance, tilt))
                n.set_pose(pose)
                self.assertLess(np.linalg.norm(pixel(cam, point)
                                               - [px, py]), 0.5)
                self.assertAlmostEqual(n.pose.distance, 0.8 * d0,
                                       delta=1e-6 * d0)

    def test_minimum_altitude(self):
        n = navigator(300.0)
        for _ in range(20):
            n.set_pose(nav.zoom(n.camera, n.pose, W / 2, H / 2, 0.5))
        self.assertAlmostEqual(nav.altitude(n.camera.eye),
                               nav.MIN_ALTITUDE, delta=0.5)

    def test_smooth_zoom_reaches_the_total(self):
        n = navigator(10000.0)
        n.wheel(W / 2, H / 2, 0.8, 0.0)
        n.wheel(W / 2, H / 2, 0.8, 0.0)
        t = 0.0
        while n.step(t):
            t += 0.016
            self.assertLess(t, 5.0)
        self.assertAlmostEqual(n.pose.distance / 10000.0, 0.64,
                               delta=0.001)


class TestOrbitDuringZoom(unittest.TestCase):

    def test_turn_does_not_cancel_zoom(self):
        n = navigator(10000.0)
        n.wheel(W / 2, H / 2, 0.8, 0.0)
        n.turn(10.0, 20.0)
        t = 0.0
        while n.step(t):
            t += 0.016
        self.assertAlmostEqual(n.pose.distance / 10000.0, 0.8, delta=0.001)
        self.assertEqual((n.pose.heading, n.pose.tilt), (10.0, 20.0))


class TestOrbit(unittest.TestCase):

    def test_centre_stays_and_no_roll(self):
        n = navigator(3000.0, 10.0, 30.0)
        centre = nav.ground_under(n.camera, W / 2, H / 2)
        for dh, dt in ((15.0, 0.0), (0.0, 20.0), (-40.0, -10.0)):
            n.turn(dh, dt)
            self.assertLess(np.linalg.norm(pixel(n.camera, centre)
                                           - [W / 2, H / 2]), 1e-6)
            self.assertLess(abs(nav.roll(n.camera, n.pose)), ROLL)

    def test_tilt_limits(self):
        n = navigator(3000.0, 0.0, 30.0)
        n.turn(0.0, 200.0)
        self.assertEqual(n.pose.tilt, nav.MAX_TILT)
        n.turn(0.0, -300.0)
        self.assertEqual(n.pose.tilt, 0.0)

    def test_tilt_keeps_camera_above_minimum(self):
        n = navigator(60.0)
        n.turn(0.0, 85.0)
        self.assertGreaterEqual(nav.altitude(n.camera.eye),
                                nav.MIN_ALTITUDE - 0.01)
        self.assertGreater(n.pose.tilt, 0.0)


def hills(lat, lon):
    """Холмы до 3 км с периодом около 0.2°."""
    return 1500.0 + 1500.0 * math.sin(lat * 31.0) * math.cos(lon * 23.0)


class TestTerrain(unittest.TestCase):

    def terrain_navigator(self, distance, tilt=0.0, terrain=hills):
        n = navigator(distance, 30.0, tilt)
        n.set_terrain(terrain)
        return n

    def test_ground_under_lies_on_terrain(self):
        n = self.terrain_navigator(8000.0, 40.0)
        rng = np.random.default_rng(8)
        import ellipsoid as el
        for _ in range(20):
            px, py = on_earth(n.camera, rng)
            point = nav.ground_under(n.camera, px, py, hills)
            lat, lon, h = el.ecef_to_geodetic(point)
            self.assertAlmostEqual(float(h), hills(float(lat), float(lon)),
                                   delta=0.5)

    def test_drag_over_hills_keeps_the_point(self):
        n = self.terrain_navigator(5000.0, 30.0)
        rng = np.random.default_rng(9)
        t = 0.0
        for _ in range(20):
            px, py = on_earth(n.camera, rng)
            n.press(px, py, t)
            point = n.grab
            qx, qy = px + rng.uniform(-100, 100), py + rng.uniform(-100, 100)
            t += 0.02
            if n.drag(qx, qy, t):
                self.assertLess(np.linalg.norm(pixel(n.camera, point)
                                               - [qx, qy]), 0.5)
            n.release(t + 1.0)

    def test_wheel_keeps_clear_of_terrain(self):
        n = self.terrain_navigator(3000.0, 0.0)
        for _ in range(30):
            pose = nav.zoom(n.camera, n.pose, W / 2, H / 2, 0.5)
            if pose is not None:
                n.set_pose(pose)
        self.assertGreaterEqual(nav.clearance(n.camera.eye, hills),
                                nav.MIN_ALTITUDE - 0.5)
        self.assertLess(nav.clearance(n.camera.eye, hills), 200.0)

    def test_tilt_keeps_clear_of_terrain(self):
        n = self.terrain_navigator(300.0, 0.0)
        n.turn(0.0, 85.0)
        self.assertGreaterEqual(nav.clearance(n.camera.eye, hills),
                                nav.MIN_ALTITUDE - 0.5)

    def test_nearest_terrain_on_steep_slope(self):
        # Склон 45° к северу, глаз в 150 м над ним по отвесу. Ближайшая
        # точка склона в 106 м. Ближняя плоскость от зазора 150 м
        # срезала склон перед камерой в низком полёте у Эльбруса.
        import ellipsoid as el
        lat0, lon0 = 43.3, 42.4

        def slope(lat, lon):
            return 3000.0 + (lat - lat0) * nav.M_PER_DEGREE

        eye = el.geodetic_to_ecef(lat0, lon0, 3150.0)
        true = 150.0 / math.sqrt(2.0)
        found = nav.nearest_terrain(eye, slope)
        self.assertLessEqual(found, true * 1.02)
        self.assertGreater(found, true * 0.9)
        flat = nav.nearest_terrain(eye, lambda lat, lon: 3000.0)
        self.assertAlmostEqual(flat, 150.0, delta=0.5)
        self.assertAlmostEqual(nav.nearest_terrain(eye), 3150.0, delta=0.5)
        # Высоко над рельефом кольца не опрашиваются, оценка осторожная.
        high = el.geodetic_to_ecef(lat0, lon0, 100000.0)
        self.assertAlmostEqual(nav.nearest_terrain(high, slope),
                               97000.0 - nav.MAX_TERRAIN, delta=0.5)

    def test_rising_terrain_lifts_the_camera(self):
        heights = {"value": 0.0}
        n = self.terrain_navigator(200.0, 0.0,
                                   terrain=lambda lat, lon: heights["value"])
        heights["value"] = 4000.0
        self.assertTrue(n.keep_clear())
        self.assertGreaterEqual(nav.clearance(n.camera.eye,
                                              lambda a, b: 4000.0),
                                nav.MIN_ALTITUDE - 0.5)
        self.assertAlmostEqual(n.pose.h, 4000.0)
        self.assertFalse(n.keep_clear())


class TestLookAndPan(unittest.TestCase):
    """Взгляд по сторонам и сдвиг стрелками, как в Google Earth."""

    def test_look_keeps_eye(self):
        for distance, tilt in ((3000.0, 40.0), (2.0e5, 10.0), (500.0, 70.0)):
            pose = nav.Pose(*PERM, distance, 30.0, tilt)
            eye0, _ = pose.eye_rotation()
            out = nav.look(pose, 20.0, 5.0)
            self.assertIsNotNone(out)
            eye1, _ = out.eye_rotation()
            self.assertLess(float(np.linalg.norm(eye1 - eye0)),
                            1e-3 * distance, (distance, tilt))
            self.assertAlmostEqual(out.heading, 50.0)
            self.assertAlmostEqual(out.tilt, tilt + 5.0)

    def test_look_into_sky_is_refused(self):
        pose = nav.Pose(*PERM, 3000.0, 0.0, 80.0)
        self.assertIsNone(nav.look(pose, 0.0, 10.0))

    def test_pan_moves_along_heading(self):
        north = nav.pan(nav.Pose(*PERM, 1000.0, 0.0, 0.0), 1000.0, 0.0)
        self.assertAlmostEqual((north.lat - PERM[0]) * nav.M_PER_DEGREE,
                               1000.0, delta=1.0)
        self.assertAlmostEqual(north.lon, PERM[1], places=9)
        east = nav.pan(nav.Pose(*PERM, 1000.0, 90.0, 0.0), 1000.0, 0.0)
        self.assertGreater(east.lon, PERM[1])
        right = nav.pan(nav.Pose(*PERM, 1000.0, 0.0, 0.0), 0.0, 1000.0)
        self.assertGreater(right.lon, PERM[1])

    def test_zoom_now_keeps_point(self):
        n = navigator(2.0e5, 20.0, 30.0)
        n.pose.apply(n.camera)
        point = nav.ground_under(n.camera, 1200.0, 400.0)
        self.assertTrue(n.zoom_now(1200.0, 400.0, 0.5))
        n.pose.apply(n.camera)
        p = pixel(n.camera, point)
        self.assertLess(float(np.linalg.norm(p - [1200.0, 400.0])), 0.01)
        self.assertAlmostEqual(n.pose.distance, 1.0e5, delta=1.0)


class TestInertia(unittest.TestCase):

    def flick(self, n, fps, until=3.0):
        """Бросок: три шага перетаскивания и отпускание, потом кадры."""
        n.press(W / 2, H / 2, 0.0)
        for i in range(1, 4):
            n.drag(W / 2 + 30 * i, H / 2 + 10 * i, 0.016 * i)
        started = n.release(0.05)
        t = 0.05
        frames = 0
        while n.step(t) and t < until:
            frames += 1
            t = 0.05 + frames / fps
        return started, frames

    def test_path_does_not_depend_on_frame_rate(self):
        slow, fast = navigator(5.0e5), navigator(5.0e5)
        started, frames_slow = self.flick(slow, 30)
        self.assertTrue(started)
        _, frames_fast = self.flick(fast, 144)
        self.assertGreater(frames_fast, frames_slow)
        # Последний кадр обоих прогонов - после остановки инерции,
        # поза в нём - конец пути.
        self.assertLess(np.linalg.norm(slow.camera.eye - fast.camera.eye),
                        1e-6)

    def test_inertia_moves_on_and_stops(self):
        n = navigator(5.0e5)
        n.press(W / 2, H / 2, 0.0)
        for i in range(1, 4):
            n.drag(W / 2 + 30 * i, H / 2, 0.016 * i)
        eye = n.camera.eye.copy()
        self.assertTrue(n.release(0.05))
        n.step(0.3)
        self.assertGreater(np.linalg.norm(n.camera.eye - eye), 1.0)
        t = 0.3
        while n.step(t):
            t += 0.016
        stop = -nav.INERTIA_TAU * math.log(nav.INERTIA_STOP)
        self.assertLess(t, 0.05 + stop + 0.05)

    def test_pause_before_release_kills_inertia(self):
        n = navigator(5.0e5)
        n.press(W / 2, H / 2, 0.0)
        for i in range(1, 4):
            n.drag(W / 2 + 30 * i, H / 2, 0.016 * i)
        self.assertFalse(n.release(0.048 + 0.061))
        self.assertFalse(n.step(0.2))

    def test_press_stops_inertia(self):
        n = navigator(5.0e5)
        n.press(W / 2, H / 2, 0.0)
        n.drag(W / 2 + 40, H / 2, 0.016)
        n.release(0.02)
        self.assertIsNotNone(n.inertia)
        n.press(W / 2, H / 2, 0.03)
        self.assertIsNone(n.inertia)


if __name__ == "__main__":
    unittest.main()
